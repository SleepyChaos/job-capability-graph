from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from test_clustering_service import _seed_cluster_fixture

from app.db.base import Base
from app.modules.clustering.service import run_full_clustering
from app.modules.talent.models import (
    CandidateMatchDimensionResult,
    CandidateMatchResult,
    CandidateProfileVersion,
)
from app.modules.talent.service import (
    answer_match_evidence_question,
    answer_profile_question,
    create_learning_path,
    create_profile_draft,
    create_profile_version,
    get_match_evidence_question,
    publish_profile,
    run_matching,
    save_job_requirement_expression,
)
from app.modules.taxonomy.models import TechnologyAlias, TechnologyNode


def test_candidate_profile_match_gap_and_learning_path_are_version_bound(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        parse_run_code = _seed_cluster_fixture(session)
        technology = session.scalar(select(TechnologyNode).where(TechnologyNode.level_code == "L3"))
        session.add(
            TechnologyAlias(
                technology_node_id=technology.technology_node_id,
                source_spreadsheet_row_id=1,
                alias_text="合成机器人控制",
                normalized_alias="合成机器人控制",
                alias_type_code="standard_name",
                is_matchable=True,
            )
        )
        session.commit()
        run_full_clustering(session, parse_run_code=parse_run_code)

        draft = create_profile_draft(
            session,
            source_name="林舟_合成简历.txt",
            mime_type="text/plain",
            input_type_code="txt",
            content_text=(
                "姓名：林舟\n求职意向：机器人控制算法工程师\n硕士·控制科学与工程\n"
                "负责合成机器人控制项目，实现控制算法开发和实验验证。"
            ),
        )
        assert draft["skill_count"] == 1
        assert draft["next_question"]["turn_no"] == 1
        first = answer_profile_question(
            session,
            version_code=draft["version_code"],
            answer_text="主导控制算法实现并完成跟踪误差验证。",
        )
        assert first["next_question"]["turn_no"] == 2
        second = answer_profile_question(
            session,
            version_code=draft["version_code"],
            answer_text="偏向工程交付和真机验证。",
        )
        assert second["can_publish"] is True
        confirmed = publish_profile(session, version_code=draft["version_code"])
        assert confirmed["workflow_status_code"] == "confirmed"

        def fail_if_matching_calls_llm(**_: object):
            raise AssertionError("机械评分链路不得调用 LLM")

        monkeypatch.setattr("app.infrastructure.llm.generate", fail_if_matching_calls_llm)

        match = run_matching(session, version_code=draft["version_code"])
        repeated_match = run_matching(session, version_code=draft["version_code"])
        assert match["result_count"] == 1
        assert repeated_match["run_code"] == match["run_code"]
        assert match["results"][0]["overall_score"] > 50
        assert match["algorithm_version"] == "r_daea_pjf_v3"
        assert match["results"][0]["score_interval"]["lower"] <= match["results"][0][
            "overall_score"
        ]
        assert match["results"][0]["overall_score"] <= match["results"][0][
            "score_interval"
        ]["upper"]
        assert match["results"][0]["decision"]["status"] in {
            "safe_match",
            "safe_nonmatch",
            "needs_evidence",
            "human_review",
        }
        recommendation = match["results"][0]["recommendation"]
        assert recommendation["requirement_expression"] is not None
        assert recommendation["requirement_proof"]["operator"] in {"AND", "MUST"}
        assert recommendation["acquisition_policy"]["llm_used_for_selection"] is False
        assert recommendation["acquisition_policy"]["reference_date"] == "2026-08-10"
        assert "minimal_improvement_sets" in recommendation
        matched_result = session.scalar(
            select(CandidateMatchResult).where(
                CandidateMatchResult.result_code == match["results"][0]["result_code"]
            )
        )
        saved_expression = save_job_requirement_expression(
            session,
            job_cluster_version_id=matched_result.job_cluster_version_id,
            expression_payload={
                "operator": "MUST",
                "technology_node_id": technology.technology_node_id,
                "hard": True,
            },
        )
        assert saved_expression["expression_version_no"] == 1
        rematch = run_matching(session, version_code=draft["version_code"])
        assert rematch["run_code"] != match["run_code"]
        assert (
            rematch["results"][0]["recommendation"]["acquisition_policy"][
                "requirement_source"
            ]
            == "human_confirmed_expression"
        )
        dimensions = match["results"][0]["dimensions"]
        assert len(dimensions) == 10
        assert dimensions[0]["code"] == "required_capability_fit"
        assert {item["code"] for item in dimensions} >= {
            "required_capability_fit",
            "proficiency_fit",
            "task_semantic_fit",
            "transferable_fit",
        }
        dimension_row_count = session.scalar(
            select(func.count()).select_from(CandidateMatchDimensionResult)
        )
        assert dimension_row_count == 20
        gaps = match["results"][0]["gaps"]
        assert all(
            gap["gap_type_code"]
            in {
                "confirmed_missing",
                "evidence_insufficient",
                "depth_insufficient",
                "transferable",
                "low_confidence_requirement",
            }
            for gap in gaps
        )
        path = create_learning_path(session, result_code=match["results"][0]["result_code"])
        assert path["algorithm_version"] == "gap_path_topo_v1"
        assert all(step["evidence_reference"].startswith("gap:") for step in path["steps"])
        assert all(
            dependency < step["step_no"]
            for step in path["steps"]
            for dependency in step["depends_on"]
        )

        revised = create_profile_version(
            session,
            version_code=draft["version_code"],
            target_role_text="机器人系统工程师",
        )
        original = session.scalar(
            select(CandidateProfileVersion).where(
                CandidateProfileVersion.version_code == draft["version_code"]
            )
        )
        assert revised["version_no"] == 2
        assert revised["workflow_status_code"] == "draft"
        assert original.workflow_status_code == "confirmed"


def test_decision_aware_evidence_question_creates_audited_profile_version() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        parse_run_code = _seed_cluster_fixture(session)
        run_full_clustering(session, parse_run_code=parse_run_code)
        draft = create_profile_draft(
            session,
            source_name="证据不完整简历.txt",
            mime_type="text/plain",
            input_type_code="txt",
            content_text=(
                "姓名：周宁\n求职意向：机器人控制算法工程师\n"
                "硕士学历，参与过智能装备项目，当前简历未展开具体工具和个人职责。"
            ),
        )
        assert draft["skill_count"] == 0
        answer_profile_question(
            session,
            version_code=draft["version_code"],
            answer_text="参与智能装备项目并负责实验资料整理。",
        )
        answer_profile_question(
            session,
            version_code=draft["version_code"],
            answer_text="偏向工程实现与验证。",
        )
        publish_profile(session, version_code=draft["version_code"])

        first_match = run_matching(session, version_code=draft["version_code"])
        first_result = first_match["results"][0]
        assert first_result["decision"]["status"] == "needs_evidence"
        question = get_match_evidence_question(
            session, result_code=first_result["result_code"]
        )
        assert question["can_answer"] is True
        assert question["llm_used_for_selection"] is False
        assert question["next_evidence_question"]["technology_name"] == "合成机器人控制"
        assert question["next_evidence_question"]["value_components"]["privacy_risk"] >= 0
        assert (
            question["next_evidence_question"]["selection_method"]
            == "one_step_expected_and_robust_voi"
        )
        assert question["next_evidence_question"]["outcome_simulations"]

        update = answer_match_evidence_question(
            session,
            result_code=first_result["result_code"],
            answer_text=(
                "2025年机器人项目中，我负责合成机器人控制算法开发，"
                "完成跟踪误差实验验证并提交代码与实验指标。"
            ),
        )
        assert update["evidence_update"]["evidence_state"] == "contextual"
        assert update["profile"]["version_no"] == 2
        assert update["profile"]["workflow_status_code"] == "confirmed"
        updated_result = update["match"]["results"][0]
        assert updated_result["overall_score"] > first_result["overall_score"]
        assert updated_result["score_interval"]["width"] < first_result["score_interval"][
            "width"
        ]
        assert any(
            skill["evidence_level_code"] == "contextual"
            for skill in update["profile"]["skills"]
        )

        negative_update = answer_match_evidence_question(
            session,
            result_code=first_result["result_code"],
            answer_text="我没有使用过这项技术，也没有相关项目经验。",
        )
        assert negative_update["evidence_update"]["evidence_state"] == "confirmed_missing"
        negative_result = negative_update["match"]["results"][0]
        assert negative_result["decision"]["status"] == "safe_nonmatch"
        assert negative_result["score_interval"]["upper"] <= 59.0
        assert negative_result["recommendation"]["hard_constraints"]["failed"] is True
        assert negative_result["recommendation"]["next_evidence_question"] is None
