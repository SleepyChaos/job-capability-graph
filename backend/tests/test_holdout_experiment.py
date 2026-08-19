import hashlib
import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from test_clustering_service import _seed_cluster_fixture

from app.db.base import Base
from app.modules.clustering.models import (
    JobRole,
    JobRoleVersion,
    JobRoleVersionRequirement,
)
from app.modules.clustering.service import run_full_clustering
from app.modules.discovery.models import DiscoveryRun
from app.modules.discovery.service import _role_capability_profiles
from app.modules.job.models import (
    EvidenceSpan,
    JobParseRun,
    JobPosting,
    JobRequirement,
    TechnologyMatchAssessment,
)
from app.modules.taxonomy.models import TechnologyNode
from tools.run_holdout_experiment import (
    DEFAULT_TEMPLATE_PATH,
    CandidateProfile,
    HoldoutExperimentError,
    build_mask_set,
    eligible_mask_roles,
    evaluate,
    main,
    run_experiment,
    write_outputs,
)


def _candidate(code: str, score: float, technologies: set[int]) -> CandidateProfile:
    return CandidateProfile(
        candidate_code=code,
        score=score,
        technology_ids=frozenset(technologies),
        classification_code="potential_new_role",
    )


def _seed_technology_nodes(session: Session, node_ids: list[int]) -> None:
    """岗位画像按技术编码比较，节点必须真实存在才能把 id 映射成编码。"""
    for node_id in node_ids:
        if session.get(TechnologyNode, node_id) is not None:
            continue
        session.add(
            TechnologyNode(
                technology_node_id=node_id,
                taxonomy_version_id=1,
                technology_code=f"T9.99.{node_id:02d}",
                source_spreadsheet_row_id=node_id,
                level_code="L3",
                technology_name=f"技术{node_id}",
                normalized_name=f"技术{node_id}",
            )
        )
    session.flush()


def _seed_role(session: Session, name: str, technologies: list[int]) -> int:
    _seed_technology_nodes(session, technologies)
    role = JobRole(
        role_code=f"ROLE-HOLDOUT-{name}",
        canonical_name=name,
        normalized_name=name,
        origin_type_code="cluster_derived",
        lifecycle_status_code="active",
    )
    session.add(role)
    session.flush()
    version = JobRoleVersion(
        job_role_id=role.job_role_id,
        version_no=1,
        valid_from=date(2026, 1, 1),
        role_name=name,
        one_line_definition="合成测试岗位",
        core_responsibility_text="合成",
        approval_status_code="approved",
    )
    session.add(version)
    session.flush()
    for technology in technologies:
        session.add(
            JobRoleVersionRequirement(
                job_role_version_id=version.job_role_version_id,
                technology_node_id=technology,
                requirement_type_code="required",
                long_term_importance_score=Decimal("80"),
                recent_activity_score=Decimal("50"),
                trend_status_code="insufficient_history",
                confidence_score=Decimal("80"),
            )
        )
    session.commit()
    return role.job_role_id


def _seed_experiment_world(session: Session) -> int:
    """在既有聚类夹具上补第二个技术词,构造「岗位对 = 候选技术组合」的可复现场景。

    相似岗位(3 份)各自追加第二条已接受技术评估后,推演会产出唯一的技术对候选;
    再登记一个技术集合恰为该组合的正式岗位,遮蔽它之后候选应被重新发现。
    """
    parse_run_code = _seed_cluster_fixture(session)
    run_full_clustering(session, parse_run_code=parse_run_code)
    parse_run = session.scalar(select(JobParseRun))
    parent = session.scalar(select(TechnologyNode).where(TechnologyNode.level_code == "L2"))
    control = session.scalar(select(TechnologyNode).where(TechnologyNode.level_code == "L3"))
    vision = TechnologyNode(
        taxonomy_version_id=parse_run.taxonomy_version_id,
        technology_code="SYNTH-T2-L3",
        parent_technology_node_id=parent.technology_node_id,
        source_spreadsheet_row_id=2,
        level_code="L3",
        technology_name="合成机器视觉",
        normalized_name="合成机器视觉",
    )
    session.add(vision)
    session.flush()
    similar = list(
        session.scalars(
            select(JobPosting).where(JobPosting.job_title_normalized == "机器人控制算法工程师")
        )
    )
    assert len(similar) == 3
    for index, posting in enumerate(similar):
        requirement = JobRequirement(
            job_posting_id=posting.job_posting_id,
            taxonomy_version_id=parse_run.taxonomy_version_id,
            requirement_no=2,
            requirement_type_code="required",
            raw_term="合成机器视觉",
            raw_text="要求掌握合成机器视觉",
            technology_node_id=vision.technology_node_id,
            mention_count=1,
            confidence_score=Decimal("95"),
        )
        session.add(requirement)
        session.flush()
        span = EvidenceSpan(
            source_document_version_id=posting.source_document_version_id,
            span_type_code="requirement",
            evidence_text="要求掌握合成机器视觉",
            evidence_hash=f"{index + 50:064d}",
            source_reliability_score=Decimal("90"),
        )
        session.add(span)
        session.flush()
        session.add(
            TechnologyMatchAssessment(
                job_parse_run_id=parse_run.job_parse_run_id,
                job_requirement_id=requirement.job_requirement_id,
                evidence_span_id=span.evidence_span_id,
                context_type_code="technical",
                assessment_status_code="accepted",
                adjusted_support_score=Decimal("95"),
                feature_weight=Decimal("1"),
                reason_code="synthetic_accepted",
            )
        )
    session.commit()
    return _seed_role(
        session, "合成控制与视觉工程师", [control.technology_node_id, vision.technology_node_id]
    )


def test_mask_set_is_deterministic_and_ratio_bound() -> None:
    ids = list(range(1, 21))
    first = build_mask_set(ids, 0.2, seed=7)
    assert first == build_mask_set(ids, 0.2, seed=7)
    # 推导只依赖集合内容,与传入顺序无关。
    assert first == build_mask_set(sorted(ids, reverse=True), 0.2, seed=7)
    assert len(first) == 4
    assert set(first) <= set(ids)
    assert build_mask_set(ids, 0.2, seed=8) != first

    with pytest.raises(HoldoutExperimentError):
        build_mask_set([], 0.2, seed=1)
    with pytest.raises(HoldoutExperimentError):
        build_mask_set([1, 2], 0.2, seed=1)
    with pytest.raises(HoldoutExperimentError):
        build_mask_set([1], 1.5, seed=1)
    # 比例为 1 时允许遮蔽全部合格岗位(合成夹具场景)。
    assert build_mask_set([5, 9], 1.0, seed=3) == [5, 9]


def test_recall_rank_and_jaccard_are_exact() -> None:
    """构造已知排名的假候选,逐项验证 Recall@K、排名与 Jaccard 数值。"""
    candidates = [_candidate(f"c{i:02d}", 100.0 - i, {i, 100 + i}) for i in range(1, 13)]
    roles = {
        1: ("完全命中甲", frozenset({1, 101})),
        2: ("完全命中乙", frozenset({11, 111})),
        3: ("部分重合", frozenset({5, 105, 200})),
        4: ("无交集", frozenset({900, 901})),
    }
    metrics = evaluate(candidates, roles, jaccard_threshold=0.5, seed=42)

    assert metrics["masked_role_count"] == 4
    assert metrics["candidate_count"] == 12
    assert metrics["recall_at_k"] == {"10": 0.5, "25": 0.75, "50": 0.75, "100": 0.75}
    by_role = {row["role_id"]: row for row in metrics["per_masked_role"]}
    assert by_role[1]["best_rank"] == 1
    assert by_role[1]["best_jaccard"] == 1.0
    assert by_role[1]["best_candidate_code"] == "c01"
    assert by_role[2]["best_rank"] == 11
    assert by_role[3]["best_rank"] == 5
    assert by_role[3]["best_jaccard"] == pytest.approx(2 / 3)
    assert by_role[4]["best_candidate_code"] is None
    assert by_role[4]["best_rank"] is None
    assert by_role[4]["matched"] is False
    assert metrics["matched_role_count"] == 3
    assert metrics["unmatched_role_count"] == 1
    assert metrics["rank_summary"] == {
        "min": 1,
        "median": 5,
        "max": 11,
        "no_match_count": 1,
    }
    assert metrics["jaccard_summary"]["min"] == 0.0
    assert metrics["jaccard_summary"]["max"] == 1.0
    assert metrics["jaccard_summary"]["mean"] == pytest.approx(2 / 3)
    # 12 个候选全部排进 K=100,基线必然达到与模型相同的召回上界。
    assert metrics["random_baseline_recall_at_k"]["100"] == 0.75


def test_random_baseline_is_reproducible_with_same_seed() -> None:
    candidates = [_candidate(f"c{i:02d}", 50.0 - i, {i}) for i in range(1, 11)]
    roles = {
        1: ("甲", frozenset({3})),
        2: ("乙", frozenset({8})),
    }
    first = evaluate(candidates, roles, jaccard_threshold=0.5, seed=99)
    second = evaluate(candidates, roles, jaccard_threshold=0.5, seed=99)
    assert first["random_baseline_recall_at_k"] == second["random_baseline_recall_at_k"]
    other = evaluate(candidates, roles, jaccard_threshold=0.5, seed=100)
    assert (
        other["random_baseline_recall_at_k"]["100"]
        == first["random_baseline_recall_at_k"]["100"]
        == 1.0
    )


def test_excluded_role_ids_keep_masked_roles_out_of_profile_pool() -> None:
    """合成小场景:资格线过滤 + excluded_role_ids 把遮蔽岗位挡出画像池。"""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        wide = _seed_role(session, "宽岗位", [1, 2, 3, 4])
        thin = _seed_role(session, "单词岗位", [1])
        other = _seed_role(session, "另一宽岗位", [5, 6])

        eligible = eligible_mask_roles(session, date(2026, 8, 10), 2)
        assert set(eligible) == {wide, other}
        assert eligible[wide] == ("宽岗位", frozenset({1, 2, 3, 4}))
        assert thin not in eligible

        masked = build_mask_set(sorted(eligible), 1.0, seed=3)
        assert set(masked) == {wide, other}

        visible = {
            role_id
            for role_id, _ in _role_capability_profiles(
                session, date(2026, 8, 10), min_technology_count=2
            )
        }
        assert visible == {wide, other}
        after_masking = {
            role_id
            for role_id, _ in _role_capability_profiles(
                session,
                date(2026, 8, 10),
                min_technology_count=2,
                excluded_role_ids=frozenset(masked),
            )
        }
        assert after_masking == set()


def test_end_to_end_experiment_on_synthetic_fixture(tmp_path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        role_id = _seed_experiment_world(session)
        experiment = run_experiment(session, target_date=date(2026, 8, 10), mask_ratio=1.0, seed=11)

        assert experiment["masked_role_ids"] == [role_id]
        run = session.scalar(
            select(DiscoveryRun).where(DiscoveryRun.run_code == experiment["run_code"])
        )
        assert run.parameter_json["excluded_role_ids"] == [role_id]
        assert experiment["algorithm_version"] == run.algorithm_version
        assert experiment["input_snapshot_hash"] == run.input_snapshot_hash

        metrics = experiment["metrics"]
        assert metrics["masked_role_count"] == 1
        assert metrics["candidate_count"] == 1
        row = metrics["per_masked_role"][0]
        assert row["role_id"] == role_id
        assert row["best_jaccard"] == 1.0
        assert row["best_rank"] == 1
        assert row["matched"] is True
        assert metrics["recall_at_k"] == {"10": 1.0, "25": 1.0, "50": 1.0, "100": 1.0}
        assert metrics["random_baseline_recall_at_k"]["10"] == 1.0

        # 遮蔽生效:被遮蔽岗位不再出现在最近岗位比较的画像池里。
        profiles = _role_capability_profiles(
            session,
            date(2026, 8, 10),
            min_technology_count=2,
            excluded_role_ids=frozenset([role_id]),
        )
        assert role_id not in {role for role, _ in profiles}

        # 同输入 + 同 seed + 同参数:命中重放缓存,同 run_code、同指标。
        repeat = run_experiment(session, target_date=date(2026, 8, 10), mask_ratio=1.0, seed=11)
        assert repeat["run_code"] == experiment["run_code"]
        assert repeat["already_completed"] is True
        assert repeat["metrics"] == experiment["metrics"]

        paths = write_outputs(tmp_path, DEFAULT_TEMPLATE_PATH, experiment)
        report = paths["report"].read_text(encoding="utf-8")
        assert "{{" not in report
        assert experiment["input_snapshot_hash"] in report
        assert experiment["run_code"] in report

        manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
        assert "metrics" not in manifest
        assert manifest["masked_role_ids"] == [role_id]
        assert manifest["seed"] == 11
        assert manifest["mask_ratio"] == 1.0
        body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
        expected = hashlib.sha256(
            json.dumps(body, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        assert manifest["manifest_sha256"] == expected

        metrics_file = json.loads(paths["metrics"].read_text(encoding="utf-8"))
        assert metrics_file["frozen"]["input_snapshot_hash"] == run.input_snapshot_hash
        assert metrics_file["frozen"]["algorithm_version"] == run.algorithm_version
        assert metrics_file["frozen"]["parameter_snapshot"] == run.parameter_json
        assert metrics_file["metrics"] == experiment["metrics"]


def test_cli_defaults_to_dry_run_and_executes_only_with_flag(tmp_path, capsys) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        _seed_experiment_world(session)
    output_dir = tmp_path / "reports"
    argv = [
        "--target-date",
        "2026-08-10",
        "--mask-ratio",
        "1.0",
        "--seed",
        "11",
        "--output-dir",
        str(output_dir),
    ]

    assert main(argv, session_factory=factory) == 0
    captured = capsys.readouterr().out
    assert "dry-run" in captured
    assert "excluded_role_ids" in captured
    assert list(output_dir.glob("**/*")) == []
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(DiscoveryRun)) == 0

    assert main([*argv, "--execute"], session_factory=factory) == 0
    assert len(list(output_dir.iterdir())) == 3
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(DiscoveryRun)) == 1
    executed = capsys.readouterr().out
    assert "run_code" in executed
