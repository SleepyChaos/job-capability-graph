import pytest

from app.modules.talent.acquisition import (
    ScoreProjection,
    plan_evidence_questions,
    plan_minimal_improvement_sets,
)
from app.modules.talent.evidence_state import (
    EvidenceState,
    EvidenceValue,
    InvalidEvidenceTransition,
    interval_is_refinement,
    transition_evidence,
)
from app.modules.talent.requirement_dsl import (
    RequirementContext,
    RequirementNode,
    RequirementOperator,
    evaluate_requirement,
)


def skill(
    technology_id: int,
    *,
    operator: RequirementOperator = RequirementOperator.MUST,
    hard: bool = True,
) -> RequirementNode:
    return RequirementNode(
        operator=operator,
        technology_node_id=technology_id,
        hard=hard,
    )


def test_evidence_state_transition_requires_verification() -> None:
    unknown = EvidenceValue.for_state(EvidenceState.UNKNOWN, source_ids=("resume:1",))
    contextual = transition_evidence(
        unknown,
        EvidenceState.CONTEXTUAL,
        source_ids=("dialogue:1",),
    )

    assert interval_is_refinement(unknown, contextual)
    assert contextual.source_ids == ("resume:1", "dialogue:1")
    with pytest.raises(InvalidEvidenceTransition):
        transition_evidence(contextual, EvidenceState.VERIFIED)

    verified = transition_evidence(
        contextual,
        EvidenceState.VERIFIED,
        verification_present=True,
        source_ids=("verification:1",),
    )
    assert verified.lower == verified.upper == 1.0


def test_or_requirement_preserves_unknown_instead_of_marking_missing() -> None:
    expression = RequirementNode(
        operator=RequirementOperator.OR,
        children=(skill(1), skill(2)),
        hard=True,
    )
    context = RequirementContext(
        skills={
            1: EvidenceValue.for_state(EvidenceState.CONFIRMED_MISSING),
            2: EvidenceValue.for_state(EvidenceState.UNKNOWN),
        }
    )

    result = evaluate_requirement(expression, context)

    assert result.lower == 0.0
    assert result.upper == 1.0
    assert result.hard_failed is False
    assert result.failed_technology_ids == ()
    assert result.unresolved_technology_ids == (2,)


def test_k_of_n_truth_table_and_hard_failure() -> None:
    expression = RequirementNode(
        operator=RequirementOperator.K_OF_N,
        k=2,
        children=(skill(1), skill(2), skill(3)),
        hard=True,
    )
    uncertain = evaluate_requirement(
        expression,
        RequirementContext(
            skills={
                1: EvidenceValue.for_state(EvidenceState.VERIFIED),
                2: EvidenceValue.for_state(EvidenceState.UNKNOWN),
                3: EvidenceValue.for_state(EvidenceState.CONFIRMED_MISSING),
            }
        ),
    )
    failed = evaluate_requirement(
        expression,
        RequirementContext(
            skills={
                1: EvidenceValue.for_state(EvidenceState.VERIFIED),
                2: EvidenceValue.for_state(EvidenceState.CONFIRMED_MISSING),
                3: EvidenceValue.for_state(EvidenceState.CONFIRMED_MISSING),
            }
        ),
    )

    assert uncertain.lower == 0.5
    assert uncertain.upper == 1.0
    assert uncertain.hard_failed is False
    assert failed.lower == failed.upper == 0.5
    assert failed.hard_failed is True


def test_years_recent_and_level_propagate_ranges() -> None:
    context = RequirementContext(
        skills={
            1: EvidenceValue.for_state(
                EvidenceState.CONTEXTUAL,
                minimum_months=24,
                maximum_months=48,
                months_since_last_use_lower=6,
                months_since_last_use_upper=18,
                level_lower=2,
                level_upper=4,
            )
        }
    )
    years = RequirementNode(
        operator=RequirementOperator.YEARS,
        technology_node_id=1,
        minimum_years=3,
        hard=True,
    )
    recent = RequirementNode(
        operator=RequirementOperator.RECENT,
        technology_node_id=1,
        maximum_months=12,
        hard=True,
    )
    level = RequirementNode(
        operator=RequirementOperator.LEVEL,
        technology_node_id=1,
        minimum_level=3,
        hard=True,
    )

    for expression in (years, recent, level):
        result = evaluate_requirement(expression, context)
        assert result.lower == 0.0
        assert result.upper == 1.0
        assert result.hard_failed is False


def test_one_step_voi_simulates_answer_outcomes_and_resolves_threshold() -> None:
    expression = RequirementNode(
        operator=RequirementOperator.AND,
        children=(skill(1), skill(2)),
    )
    context = RequirementContext(
        skills={
            1: EvidenceValue.for_state(EvidenceState.VERIFIED),
            2: EvidenceValue.for_state(EvidenceState.UNKNOWN),
        }
    )

    plans = plan_evidence_questions(expression, context, threshold=0.60)

    assert len(plans) == 1
    plan = plans[0]
    assert plan.technology_node_id == 2
    assert plan.net_utility > 0
    assert plan.expected_interval_shrink > 0
    assert plan.threshold_resolution_probability == pytest.approx(0.75)
    assert {item["outcome_state"] for item in plan.outcome_simulations} == {
        "confirmed_missing",
        "self_claim",
        "contextual",
        "verified",
    }


def test_voi_projects_requirement_outcomes_into_overall_score() -> None:
    expression = RequirementNode(
        operator=RequirementOperator.MUST,
        technology_node_id=7,
        hard=True,
    )

    plans = plan_evidence_questions(
        expression,
        RequirementContext(skills={}),
        score_projection=ScoreProjection(
            fixed_lower=0.40,
            fixed_upper=0.40,
            requirement_weight=0.30,
            overall_threshold=0.60,
            hard_score_cap=0.59,
        ),
    )

    outcomes = {item["outcome_state"]: item for item in plans[0].outcome_simulations}
    assert outcomes["verified"]["decision"] == "safe_match"
    assert outcomes["verified"]["lower"] == pytest.approx(0.70)
    assert outcomes["confirmed_missing"]["decision"] == "safe_nonmatch"


def test_minimal_improvement_set_requires_the_smallest_complete_combination() -> None:
    expression = RequirementNode(
        operator=RequirementOperator.AND,
        children=(skill(1), skill(2), skill(3)),
    )
    context = RequirementContext(
        skills={
            1: EvidenceValue.for_state(EvidenceState.VERIFIED),
            2: EvidenceValue.for_state(EvidenceState.UNKNOWN),
            3: EvidenceValue.for_state(EvidenceState.UNKNOWN),
        }
    )

    plans = plan_minimal_improvement_sets(
        expression,
        context,
        threshold=0.80,
    )

    assert len(plans) == 1
    assert set(plans[0].technology_node_ids) == {2, 3}
    assert plans[0].projected_lower == pytest.approx(1.0)
    assert plans[0].to_dict()["warning"].startswith("projection_only")


def test_requirement_expression_round_trip_and_proof_tree() -> None:
    payload = {
        "operator": "AND",
        "children": [
            {"operator": "MUST", "technology_node_id": 1, "evidence_refs": ["job:1"]},
            {
                "operator": "OR",
                "hard": True,
                "children": [
                    {"operator": "SKILL", "technology_node_id": 2},
                    {"operator": "SKILL", "technology_node_id": 3},
                ],
            },
        ],
    }
    expression = RequirementNode.from_dict(payload)
    result = evaluate_requirement(
        expression,
        RequirementContext(
            skills={
                1: EvidenceValue.for_state(EvidenceState.VERIFIED),
                2: EvidenceValue.for_state(EvidenceState.CONTEXTUAL),
                3: EvidenceValue.for_state(EvidenceState.CONFIRMED_MISSING),
            }
        ),
    )

    assert expression.to_dict()["operator"] == "AND"
    assert result.proof["children"][0]["evidence_refs"] == ["job:1"]
    assert result.proof["children"][1]["operator"] == "OR"
