from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from test_clustering_service import _seed_cluster_fixture

from app.db.base import Base
from app.modules.clustering.models import JobRole, JobRoleVersion
from app.modules.clustering.service import run_full_clustering
from app.modules.data_center.models import AppUser, ReviewTask
from app.modules.discovery.models import DiscoveryRun, EmergingRoleCandidate, StandardJobDescription
from app.modules.discovery.service import (
    DiscoveryError,
    apply_candidate_expression,
    review_candidate,
    run_discovery,
)
from app.modules.job.models import JobParseRun, JobPosting, TechnologyMatchAssessment
from app.modules.taxonomy.models import TechnologyNode


def test_replay_cache_detects_changed_job_collection_times() -> None:
    """采集时间决定观测窗，改了它必须重算，不能命中上一次运行的重放缓存。"""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        parse_run_code = _seed_cluster_fixture(session)
        run_full_clustering(session, parse_run_code=parse_run_code)
        first = run_discovery(session, mode_code="automatic", target_date=date(2026, 8, 10))
        assert (
            run_discovery(
                session, mode_code="automatic", target_date=date(2026, 8, 10)
            ).already_completed
            is True
        )

        # 时间戳仍在 cutoff 之前，因此"哪些技术评估可用"完全不变，只有观测窗变了。
        moved = session.scalars(
            select(JobPosting).where(JobPosting.source_collected_at.is_not(None))
        ).all()
        for posting in moved:
            posting.source_collected_at = datetime(2026, 8, 1)
        session.commit()

        second = run_discovery(session, mode_code="automatic", target_date=date(2026, 8, 10))

        assert second.already_completed is False
        assert second.run_code != first.run_code


def test_discovery_evidence_stays_within_its_clustering_generation() -> None:
    """JD 更新会产生新的解析运行；推演的证据必须与其绑定的聚类运行同源。"""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        parse_run_code = _seed_cluster_fixture(session)
        run_full_clustering(session, parse_run_code=parse_run_code)
        baseline = run_discovery(session, mode_code="automatic", target_date=date(2026, 8, 10))
        candidate = session.scalar(select(EmergingRoleCandidate))
        baseline_evidence = len(candidate.mechanical_card_json["evidence_ids"])
        baseline_jobs = candidate.mechanical_card_json["job_count"]

        # 模拟"又解析了一次"：复制一份已接受评估挂到新的解析运行下。
        old_run = session.scalar(select(JobParseRun))
        newer = JobParseRun(
            run_code="jdparse_second_generation",
            target_date=old_run.target_date,
            taxonomy_version_id=old_run.taxonomy_version_id,
            parser_version=old_run.parser_version,
            input_snapshot_hash="second-generation-hash",
            run_status_code="completed",
        )
        session.add(newer)
        session.flush()
        for assessment in session.scalars(
            select(TechnologyMatchAssessment).where(
                TechnologyMatchAssessment.job_parse_run_id == old_run.job_parse_run_id
            )
        ).all():
            session.add(
                TechnologyMatchAssessment(
                    job_parse_run_id=newer.job_parse_run_id,
                    job_requirement_id=assessment.job_requirement_id,
                    evidence_span_id=assessment.evidence_span_id,
                    context_type_code=assessment.context_type_code,
                    assessment_status_code="accepted",
                    adjusted_support_score=assessment.adjusted_support_score,
                    feature_weight=assessment.feature_weight,
                    reason_code=assessment.reason_code,
                )
            )
        session.commit()

        after = run_discovery(
            session,
            mode_code="automatic",
            target_date=date(2026, 8, 10),
            parameters={"probe": "second-generation"},
        )
        refreshed = session.scalar(
            select(EmergingRoleCandidate)
            .join(
                DiscoveryRun,
                DiscoveryRun.discovery_run_id == EmergingRoleCandidate.discovery_run_id,
            )
            .where(DiscoveryRun.run_code == after.run_code)
        )

        # 新一代解析未被本次聚类采用，证据量不得因此膨胀。
        assert len(refreshed.mechanical_card_json["evidence_ids"]) == baseline_evidence
        assert refreshed.mechanical_card_json["job_count"] == baseline_jobs
        assert baseline.run_code != after.run_code


def test_discovery_is_replayable_and_publishes_separate_standard_jd() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        parse_run_code = _seed_cluster_fixture(session)
        run_full_clustering(session, parse_run_code=parse_run_code)
        reviewer = AppUser(
            user_code="DISCOVERY-REVIEWER",
            display_name="专项审批员",
            role_code="reviewer",
        )
        session.add(reviewer)
        session.commit()

        result = run_discovery(
            session,
            mode_code="automatic",
            target_date=date(2026, 8, 10),
        )
        repeated = run_discovery(
            session,
            mode_code="automatic",
            target_date=date(2026, 8, 10),
        )

        assert result.candidate_count == 1
        assert result.evidence_limited is True
        assert repeated.already_completed is True
        candidate = session.scalar(select(EmergingRoleCandidate))
        assert candidate is not None
        assert candidate.maturity_stage_code == "potential"
        assert "insufficient_temporal_history" in candidate.risk_flags_json
        task = session.scalar(select(ReviewTask).where(ReviewTask.queue_code == "job_discovery"))
        assert task is not None
        with pytest.raises(DiscoveryError, match="事实ID"):
            apply_candidate_expression(
                session,
                candidate_code=candidate.candidate_code,
                proposed_name="优化后的岗位名",
                one_line_definition="合成定义",
                core_responsibilities=["合成职责"],
                formation_reason="合成原因",
                difference_explanation="合成差异",
                fact_references=["evidence:not-real"],
                model_version="synthetic-llm-v1",
            )
        candidate = apply_candidate_expression(
            session,
            candidate_code=candidate.candidate_code,
            proposed_name="合成机器人控制工程师",
            one_line_definition="负责合成机器人控制工程任务。",
            core_responsibilities=["完成合成机器人控制算法开发"],
            formation_reason="基于跨企业JD职责证据形成。",
            difference_explanation="与已有岗位的能力组合不同。",
            fact_references=[f"evidence:{candidate.mechanical_card_json['evidence_ids'][0]}"],
            model_version="synthetic-llm-v1",
        )
        assert candidate.mechanical_card_json["job_count"] == 3
        assert candidate.expression_model_version == "synthetic-llm-v1"

        approved = review_candidate(
            session,
            task_code=task.task_code,
            action_code="approve",
            actor_user_id=reviewer.user_id,
            comment_text="合成闭环审批",
        )

        assert approved.workflow_status_code == "approved"
        assert approved.maturity_stage_code == "confirmed"
        role = session.get(JobRole, approved.approved_job_role_id)
        assert role is not None and role.origin_type_code == "inference_derived"
        version = session.scalar(
            select(JobRoleVersion).where(JobRoleVersion.job_role_id == role.job_role_id)
        )
        assert version is not None and version.approval_status_code == "approved"
        standard_jd = session.scalar(select(StandardJobDescription))
        assert standard_jd is not None and standard_jd.is_market_evidence is False
        assert session.scalar(select(func.count()).select_from(DiscoveryRun)) == 1

        technology_id = session.scalar(
            select(TechnologyNode.technology_node_id).where(TechnologyNode.level_code == "L3")
        )
        directed = run_discovery(
            session,
            mode_code="technology_directed",
            target_date=date(2026, 8, 10),
            selected_technology_ids=[technology_id],
        )
        assert directed.candidate_count == 1

        existing_name = run_discovery(
            session,
            mode_code="name_inference",
            target_date=date(2026, 8, 10),
            query_role_name=role.canonical_name,
        )
        existing_candidate = session.scalar(
            select(EmergingRoleCandidate).where(
                EmergingRoleCandidate.discovery_run_id
                == session.scalar(
                    select(DiscoveryRun.discovery_run_id).where(
                        DiscoveryRun.run_code == existing_name.run_code
                    )
                )
            )
        )
        assert existing_candidate.classification_code == "existing_role"
        assert existing_candidate.workflow_status_code == "merged"

        unsupported = run_discovery(
            session,
            mode_code="name_inference",
            target_date=date(2026, 8, 10),
            query_role_name="没有任何证据的未来岗位",
        )
        unsupported_candidate = session.scalar(
            select(EmergingRoleCandidate).where(
                EmergingRoleCandidate.discovery_run_id
                == session.scalar(
                    select(DiscoveryRun.discovery_run_id).where(
                        DiscoveryRun.run_code == unsupported.run_code
                    )
                )
            )
        )
        unsupported_task = session.scalar(
            select(ReviewTask).where(
                ReviewTask.target_id == unsupported_candidate.emerging_role_candidate_id,
                ReviewTask.queue_code == "job_discovery",
            )
        )
        with pytest.raises(DiscoveryError, match="缺少可追溯"):
            review_candidate(
                session,
                task_code=unsupported_task.task_code,
                action_code="approve",
                actor_user_id=reviewer.user_id,
            )
