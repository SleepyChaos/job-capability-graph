from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.infrastructure.llm import LLMResult
from app.modules.job.llm_reassessment_service import (
    LlmTechnologyReassessmentService,
    ReassessmentTarget,
)
from app.modules.job.models import (
    JobClusterFeatureSnapshot,
    LlmTechnologyReassessment,
    TechnologyMatchAssessment,
)
from tests.test_clustering_service import _seed_cluster_fixture


def _target(context: str = "负责汽车生产线装配工艺和质量改善") -> ReassessmentTarget:
    return ReassessmentTarget(
        assessment=SimpleNamespace(
            technology_match_assessment_id=17,
            context_type_code="responsibility",
        ),
        requirement=SimpleNamespace(raw_term="汽车"),
        job=SimpleNamespace(job_title_normalized="制造工艺工程师"),
        technology=SimpleNamespace(
            technology_code="T7.01.04",
            technology_name="汽车制造",
            level_code="L3",
            definition_text="汽车生产与制造工艺",
        ),
        parent_technology_name="工业制造场景",
        evidence_text="汽车",
        context_text=context,
        input_hash="a" * 64,
    )


def test_validate_response_accepts_only_quote_from_context() -> None:
    normalized, status = LlmTechnologyReassessmentService._validate_response(
        _target(),
        {
            "assessment_id": 17,
            "decision": "accepted",
            "confidence": 0.93,
            "evidence_quote": "汽车生产线装配工艺",
            "reason_code": "semantic_context",
            "reason": "上下文明确描述汽车制造产线。",
        },
    )

    assert status == "valid"
    assert normalized["decision"] == "accepted"
    assert normalized["confidence"] == Decimal("0.930000")


def test_validate_response_rejects_hallucinated_quote() -> None:
    normalized, status = LlmTechnologyReassessmentService._validate_response(
        _target(),
        {
            "assessment_id": 17,
            "decision": "accepted",
            "confidence": 0.99,
            "evidence_quote": "负责自动驾驶算法开发",
            "reason_code": "semantic_context",
            "reason": "模型补充了不存在的证据。",
        },
    )

    assert status == "invalid_evidence_quote"
    assert normalized["decision"] == "uncertain"
    assert normalized["confidence"] is None


def test_prompt_is_closed_set_and_keeps_candidate_code() -> None:
    item = LlmTechnologyReassessmentService._prompt_item(_target())
    system_prompt = LlmTechnologyReassessmentService._system_prompt()

    assert item["candidate_technology"]["code"] == "T7.01.04"
    assert item["context"] == "负责汽车生产线装配工艺和质量改善"
    assert "不得新增、替换或猜测技术编码" in system_prompt


def test_diverse_targets_round_robins_rules_and_jobs() -> None:
    targets = []
    for assessment_id, rule_id, job_id in [
        (1, 10, 1),
        (2, 10, 1),
        (3, 10, 2),
        (4, 20, 3),
        (5, 20, 4),
    ]:
        target = _target()
        object.__setattr__(
            target,
            "assessment",
            SimpleNamespace(
                technology_match_assessment_id=assessment_id,
                context_type_code="required",
                ambiguity_rule_id=rule_id,
            ),
        )
        object.__setattr__(target, "job", SimpleNamespace(job_posting_id=job_id))
        targets.append(target)

    sampled = LlmTechnologyReassessmentService._diverse_targets(targets, 4)

    assert [item.assessment.technology_match_assessment_id for item in sampled] == [1, 4, 3, 5]


def test_service_applies_valid_closed_set_decision_and_refreshes_feature() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        parse_run_code = _seed_cluster_fixture(session)
        assessment = session.scalar(
            select(TechnologyMatchAssessment).order_by(
                TechnologyMatchAssessment.technology_match_assessment_id
            )
        )
        assert assessment is not None
        assessment.assessment_status_code = "needs_review"
        assessment.adjusted_support_score = Decimal("35")
        assessment.feature_weight = Decimal("0.35")
        assessment.reason_code = "ambiguity_context_missing"
        old_feature_hash = session.scalar(
            select(JobClusterFeatureSnapshot.feature_hash).where(
                JobClusterFeatureSnapshot.job_posting_id == 1
            )
        )
        session.commit()

        def fake_generator(**_: object) -> LLMResult:
            return LLMResult(
                model="deepseek-test",
                prompt_version="technology_reassessment_closed_set_v2",
                content="",
                parsed_json={
                    "items": [
                        {
                            "assessment_id": assessment.technology_match_assessment_id,
                            "decision": "accepted",
                            "confidence": 0.94,
                            "evidence_quote": "机器人控制算法",
                            "reason_code": "semantic_context",
                            "reason": "上下文明确描述该技术。",
                        }
                    ]
                },
            )

        result = LlmTechnologyReassessmentService(
            session, generator=fake_generator
        ).run(parse_run_code=parse_run_code, batch_size=1)

        session.refresh(assessment)
        audit = session.scalar(select(LlmTechnologyReassessment))
        new_feature_hash = session.scalar(
            select(JobClusterFeatureSnapshot.feature_hash).where(
                JobClusterFeatureSnapshot.job_posting_id == 1
            )
        )
        assert result.applied_count == 1
        assert result.affected_job_count == 1
        assert assessment.assessment_status_code == "accepted"
        assert assessment.reason_code == "llm_context_confirmed"
        assert assessment.feature_weight == Decimal("0.9400")
        assert audit is not None and audit.applied is True
        assert audit.validation_status_code == "valid"
        assert new_feature_hash != old_feature_hash
