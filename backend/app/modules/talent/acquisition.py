"""One-step decision-aware evidence acquisition without LLM planning."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from app.modules.talent.evidence_state import EvidenceState, EvidenceValue
from app.modules.talent.requirement_dsl import (
    RequirementContext,
    RequirementEvaluation,
    RequirementNode,
    evaluate_requirement,
)

DEFAULT_OUTCOME_PRIORS: dict[EvidenceState, float] = {
    EvidenceState.CONFIRMED_MISSING: 0.25,
    EvidenceState.SELF_CLAIM: 0.25,
    EvidenceState.CONTEXTUAL: 0.35,
    EvidenceState.VERIFIED: 0.15,
}


@dataclass(frozen=True)
class AcquisitionCosts:
    answer_cost: float = 0.14
    privacy_risk: float = 0.02
    fairness_risk: float = 0.03
    manipulation_risk: float = 0.24
    repetition_penalty: float = 0.0


@dataclass(frozen=True)
class AcquisitionWeights:
    cost: float = 0.10
    privacy: float = 0.20
    fairness: float = 0.10
    manipulation: float = 0.25
    robust_value: float = 0.30
    interval_shrink: float = 0.25
    threshold_resolution: float = 0.35


@dataclass(frozen=True)
class ScoreProjection:
    """Project the requirement interval into the deterministic overall score."""

    fixed_lower: float = 0.0
    fixed_upper: float = 0.0
    requirement_weight: float = 1.0
    overall_threshold: float = 0.60
    hard_score_cap: float = 0.59


@dataclass(frozen=True)
class QuestionPlan:
    technology_node_id: int
    expected_value_of_information: float
    robust_value_of_information: float
    expected_interval_shrink: float
    threshold_resolution_probability: float
    net_utility: float
    costs: AcquisitionCosts
    outcome_simulations: tuple[dict, ...]

    def to_dict(self) -> dict:
        return {
            "technology_node_id": self.technology_node_id,
            "expected_value_of_information": round(
                self.expected_value_of_information, 6
            ),
            "robust_value_of_information": round(
                self.robust_value_of_information, 6
            ),
            "expected_interval_shrink": round(self.expected_interval_shrink, 6),
            "threshold_resolution_probability": round(
                self.threshold_resolution_probability, 6
            ),
            "net_utility": round(self.net_utility, 6),
            "costs": {
                "answer_cost": self.costs.answer_cost,
                "privacy_risk": self.costs.privacy_risk,
                "fairness_risk": self.costs.fairness_risk,
                "manipulation_risk": self.costs.manipulation_risk,
                "repetition_penalty": self.costs.repetition_penalty,
            },
            "outcome_simulations": list(self.outcome_simulations),
            "selection_method": "one_step_expected_and_robust_voi",
        }


@dataclass(frozen=True)
class ImprovementSetPlan:
    """Smallest auditable evidence set that can make acceptance safe.

    This is a deterministic planning result, not a prediction that the
    candidate actually owns the missing evidence.  Every listed technology
    must still be collected and verified before the projected lower bound is
    used as a real decision.
    """

    technology_node_ids: tuple[int, ...]
    assumed_state: EvidenceState
    projected_lower: float
    projected_upper: float
    total_collection_cost: float

    def to_dict(self) -> dict:
        return {
            "technology_node_ids": list(self.technology_node_ids),
            "assumed_state": self.assumed_state.value,
            "projected_lower": round(self.projected_lower, 6),
            "projected_upper": round(self.projected_upper, 6),
            "total_collection_cost": round(self.total_collection_cost, 6),
            "selection_method": "bounded_minimum_safe_acceptance_set",
            "warning": (
                "projection_only: every listed item must be collected and "
                "verified before the projected decision is valid"
            ),
        }


def plan_evidence_questions(
    requirement: RequirementNode,
    context: RequirementContext,
    *,
    threshold: float = 0.60,
    outcome_priors: dict[EvidenceState, float] | None = None,
    costs_by_technology: dict[int, AcquisitionCosts] | None = None,
    weights: AcquisitionWeights | None = None,
    score_projection: ScoreProjection | None = None,
) -> list[QuestionPlan]:
    """Simulate each answer state and rank questions by deterministic utility."""
    priors = _normalized_priors(outcome_priors or DEFAULT_OUTCOME_PRIORS)
    policy_weights = weights or AcquisitionWeights()
    costs_lookup = costs_by_technology or {}
    current = evaluate_requirement(requirement, context)
    current_lower, current_upper, decision_threshold = _project_interval(
        current,
        threshold=threshold,
        projection=score_projection,
    )
    current_risk = _decision_risk(current_lower, current_upper, decision_threshold)
    current_width = current_upper - current_lower
    plans = []
    for technology_id in current.unresolved_technology_ids:
        simulations = []
        expected_risk = 0.0
        expected_width = 0.0
        resolution_probability = 0.0
        risk_improvements = []
        for state, probability in priors.items():
            simulated_skills = dict(context.skills)
            simulated_skills[technology_id] = EvidenceValue.for_state(state)
            simulated = evaluate_requirement(
                requirement,
                RequirementContext(
                    skills=simulated_skills,
                    constraints=context.constraints,
                ),
            )
            simulated_lower, simulated_upper, _ = _project_interval(
                simulated,
                threshold=threshold,
                projection=score_projection,
            )
            simulated_risk = _decision_risk(
                simulated_lower,
                simulated_upper,
                decision_threshold,
            )
            simulated_width = simulated_upper - simulated_lower
            decision = _decision_status(
                simulated_lower,
                simulated_upper,
                decision_threshold,
            )
            expected_risk += probability * simulated_risk
            expected_width += probability * simulated_width
            if decision in {"safe_match", "safe_nonmatch"}:
                resolution_probability += probability
            risk_improvements.append(current_risk - simulated_risk)
            simulations.append(
                {
                    "outcome_state": state.value,
                    "probability": round(probability, 6),
                    "requirement_lower": round(simulated.lower, 6),
                    "requirement_upper": round(simulated.upper, 6),
                    "lower": round(simulated_lower, 6),
                    "upper": round(simulated_upper, 6),
                    "decision": decision,
                    "decision_risk": round(simulated_risk, 6),
                }
            )
        expected_voi = max(0.0, current_risk - expected_risk)
        robust_voi = max(0.0, min(risk_improvements))
        expected_shrink = max(0.0, current_width - expected_width)
        costs = costs_lookup.get(technology_id, AcquisitionCosts())
        positive_value = (
            expected_voi
            + policy_weights.robust_value * robust_voi
            + policy_weights.interval_shrink * expected_shrink
            + policy_weights.threshold_resolution * resolution_probability
        )
        penalty = (
            policy_weights.cost * costs.answer_cost
            + policy_weights.privacy * costs.privacy_risk
            + policy_weights.fairness * costs.fairness_risk
            + policy_weights.manipulation * costs.manipulation_risk
            + costs.repetition_penalty
        )
        plans.append(
            QuestionPlan(
                technology_node_id=technology_id,
                expected_value_of_information=expected_voi,
                robust_value_of_information=robust_voi,
                expected_interval_shrink=expected_shrink,
                threshold_resolution_probability=resolution_probability,
                net_utility=positive_value - penalty,
                costs=costs,
                outcome_simulations=tuple(simulations),
            )
        )
    plans.sort(key=lambda item: (-item.net_utility, item.technology_node_id))
    return plans


def plan_minimal_improvement_sets(
    requirement: RequirementNode,
    context: RequirementContext,
    *,
    threshold: float = 0.60,
    costs_by_technology: dict[int, AcquisitionCosts] | None = None,
    score_projection: ScoreProjection | None = None,
    assumed_state: EvidenceState = EvidenceState.VERIFIED,
    max_set_size: int = 3,
    max_candidates: int = 12,
    limit: int = 3,
) -> list[ImprovementSetPlan]:
    """Find bounded, minimum-cardinality evidence sets for safe acceptance.

    The search is intentionally bounded so matching latency cannot grow
    combinatorially on large job expressions. Candidate technologies are
    ordered by the same one-step decision-value policy used for questioning;
    ties are stable by technology id. The result is a counterfactual plan only
    and never mutates the candidate evidence context.
    """
    if max_set_size < 1 or max_candidates < 1 or limit < 1:
        raise ValueError("minimum-set search limits must be positive")
    current = evaluate_requirement(requirement, context)
    current_lower, current_upper, decision_threshold = _project_interval(
        current,
        threshold=threshold,
        projection=score_projection,
    )
    if current_lower >= decision_threshold or current_upper < decision_threshold:
        return []

    costs_lookup = costs_by_technology or {}
    ranked_questions = plan_evidence_questions(
        requirement,
        context,
        threshold=threshold,
        costs_by_technology=costs_lookup,
        score_projection=score_projection,
    )
    candidate_ids = tuple(
        item.technology_node_id for item in ranked_questions[:max_candidates]
    )
    if not candidate_ids:
        return []

    feasible: list[ImprovementSetPlan] = []
    largest_size = min(max_set_size, len(candidate_ids))
    for set_size in range(1, largest_size + 1):
        for technology_ids in combinations(candidate_ids, set_size):
            simulated_skills = dict(context.skills)
            for technology_id in technology_ids:
                previous = context.skill(technology_id)
                simulated_skills[technology_id] = EvidenceValue.for_state(
                    assumed_state,
                    minimum_months=previous.minimum_months,
                    maximum_months=previous.maximum_months,
                    months_since_last_use_lower=previous.months_since_last_use_lower,
                    months_since_last_use_upper=previous.months_since_last_use_upper,
                    level_lower=previous.level_lower,
                    level_upper=previous.level_upper,
                    source_ids=previous.source_ids,
                )
            simulated = evaluate_requirement(
                requirement,
                RequirementContext(
                    skills=simulated_skills,
                    constraints=context.constraints,
                ),
            )
            lower, upper, _ = _project_interval(
                simulated,
                threshold=threshold,
                projection=score_projection,
            )
            if lower < decision_threshold:
                continue
            total_cost = sum(
                _collection_cost(costs_lookup.get(item, AcquisitionCosts()))
                for item in technology_ids
            )
            feasible.append(
                ImprovementSetPlan(
                    technology_node_ids=tuple(sorted(technology_ids)),
                    assumed_state=assumed_state,
                    projected_lower=lower,
                    projected_upper=upper,
                    total_collection_cost=total_cost,
                )
            )
        if feasible:
            break
    feasible.sort(
        key=lambda item: (
            len(item.technology_node_ids),
            item.total_collection_cost,
            -item.projected_lower,
            item.technology_node_ids,
        )
    )
    return feasible[:limit]


def _project_interval(
    evaluation: RequirementEvaluation,
    *,
    threshold: float,
    projection: ScoreProjection | None,
) -> tuple[float, float, float]:
    if projection is None:
        return evaluation.lower, evaluation.upper, threshold
    lower = projection.fixed_lower + projection.requirement_weight * evaluation.lower
    upper = projection.fixed_upper + projection.requirement_weight * evaluation.upper
    if evaluation.hard_failed:
        lower = min(lower, projection.hard_score_cap)
        upper = min(upper, projection.hard_score_cap)
    return lower, upper, projection.overall_threshold


def _decision_status(lower: float, upper: float, threshold: float) -> str:
    if lower >= threshold:
        return "safe_match"
    if upper < threshold:
        return "safe_nonmatch"
    return "needs_evidence"


def _decision_risk(lower: float, upper: float, threshold: float) -> float:
    if lower >= threshold or upper < threshold:
        return 0.0
    width = upper - lower
    threshold_position = (threshold - lower) / max(width, 1e-9)
    boundary_ambiguity = 1.0 - abs(0.5 - threshold_position) * 2
    return min(1.0, 0.5 * width + 0.5 * max(0.0, boundary_ambiguity))


def _normalized_priors(
    priors: dict[EvidenceState, float],
) -> dict[EvidenceState, float]:
    normalized = {EvidenceState(key): float(value) for key, value in priors.items()}
    if any(value < 0 for value in normalized.values()):
        raise ValueError("outcome prior cannot be negative")
    total = sum(normalized.values())
    if total <= 0:
        raise ValueError("outcome priors must have positive total mass")
    return {key: value / total for key, value in normalized.items()}


def _collection_cost(costs: AcquisitionCosts) -> float:
    return (
        costs.answer_cost
        + costs.privacy_risk
        + costs.fairness_risk
        + costs.manipulation_risk
        + costs.repetition_penalty
    )
