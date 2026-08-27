"""Executable job-requirement DSL and deterministic interval propagation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.modules.talent.evidence_state import EvidenceState, EvidenceValue


class RequirementOperator(StrEnum):
    AND = "AND"
    OR = "OR"
    K_OF_N = "K_OF_N"
    MUST = "MUST"
    SHOULD = "SHOULD"
    SKILL = "SKILL"
    YEARS = "YEARS"
    RECENT = "RECENT"
    LEVEL = "LEVEL"
    CONSTRAINT = "CONSTRAINT"


LEAF_OPERATORS = {
    RequirementOperator.MUST,
    RequirementOperator.SHOULD,
    RequirementOperator.SKILL,
    RequirementOperator.YEARS,
    RequirementOperator.RECENT,
    RequirementOperator.LEVEL,
}


@dataclass(frozen=True)
class RequirementNode:
    operator: RequirementOperator
    technology_node_id: int | None = None
    children: tuple[RequirementNode, ...] = ()
    k: int | None = None
    minimum_years: float | None = None
    maximum_months: int | None = None
    minimum_level: int | None = None
    constraint_code: str | None = None
    weight: float = 1.0
    hard: bool = False
    evidence_refs: tuple[str, ...] = ()

    @property
    def technology_ids(self) -> tuple[int, ...]:
        values = []
        if self.technology_node_id is not None:
            values.append(self.technology_node_id)
        for child in self.children:
            values.extend(child.technology_ids)
        return tuple(dict.fromkeys(values))

    def __post_init__(self) -> None:
        if self.weight <= 0:
            raise ValueError("requirement weight must be positive")
        if self.operator in LEAF_OPERATORS and self.technology_node_id is None:
            raise ValueError(f"{self.operator.value} requires technology_node_id")
        if self.operator in {RequirementOperator.AND, RequirementOperator.OR}:
            if not self.children:
                raise ValueError(f"{self.operator.value} requires children")
        if self.operator == RequirementOperator.K_OF_N:
            if not self.children or self.k is None or not 1 <= self.k <= len(self.children):
                raise ValueError("K_OF_N requires 1 <= k <= number of children")
        if self.operator == RequirementOperator.YEARS:
            if self.minimum_years is None or self.minimum_years < 0:
                raise ValueError("YEARS requires non-negative minimum_years")
        if self.operator == RequirementOperator.RECENT:
            if self.maximum_months is None or self.maximum_months < 0:
                raise ValueError("RECENT requires non-negative maximum_months")
        if self.operator == RequirementOperator.LEVEL:
            if self.minimum_level is None or self.minimum_level < 0:
                raise ValueError("LEVEL requires non-negative minimum_level")
        if self.operator == RequirementOperator.CONSTRAINT and not self.constraint_code:
            raise ValueError("CONSTRAINT requires constraint_code")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RequirementNode:
        if not isinstance(payload, dict):
            raise ValueError("requirement expression must be an object")
        raw_operator = payload.get("operator")
        try:
            operator = RequirementOperator(str(raw_operator).upper())
        except ValueError as exc:
            raise ValueError(f"unsupported requirement operator: {raw_operator}") from exc
        raw_children = payload.get("children") or ()
        if not isinstance(raw_children, (list, tuple)):
            raise ValueError("children must be an array")
        raw_refs = payload.get("evidence_refs") or ()
        if not isinstance(raw_refs, (list, tuple)):
            raise ValueError("evidence_refs must be an array")
        return cls(
            operator=operator,
            technology_node_id=_optional_int(payload.get("technology_node_id")),
            children=tuple(cls.from_dict(item) for item in raw_children),
            k=_optional_int(payload.get("k")),
            minimum_years=_optional_float(payload.get("minimum_years")),
            maximum_months=_optional_int(payload.get("maximum_months")),
            minimum_level=_optional_int(payload.get("minimum_level")),
            constraint_code=_optional_string(payload.get("constraint_code")),
            weight=float(payload.get("weight", 1.0)),
            hard=bool(payload.get("hard", operator == RequirementOperator.MUST)),
            evidence_refs=tuple(str(item) for item in raw_refs),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "operator": self.operator.value,
            "weight": self.weight,
            "hard": self.hard,
        }
        for key, value in (
            ("technology_node_id", self.technology_node_id),
            ("k", self.k),
            ("minimum_years", self.minimum_years),
            ("maximum_months", self.maximum_months),
            ("minimum_level", self.minimum_level),
            ("constraint_code", self.constraint_code),
        ):
            if value is not None:
                result[key] = value
        if self.children:
            result["children"] = [item.to_dict() for item in self.children]
        if self.evidence_refs:
            result["evidence_refs"] = list(self.evidence_refs)
        return result


@dataclass(frozen=True)
class RequirementContext:
    skills: dict[int, EvidenceValue] = field(default_factory=dict)
    constraints: dict[str, EvidenceValue] = field(default_factory=dict)

    def skill(self, technology_node_id: int) -> EvidenceValue:
        return self.skills.get(
            technology_node_id,
            EvidenceValue.for_state(EvidenceState.UNKNOWN),
        )

    def constraint(self, constraint_code: str) -> EvidenceValue:
        return self.constraints.get(
            constraint_code,
            EvidenceValue.for_state(EvidenceState.UNKNOWN),
        )


@dataclass(frozen=True)
class RequirementEvaluation:
    lower: float
    upper: float
    hard_failed: bool
    unresolved_technology_ids: tuple[int, ...]
    failed_technology_ids: tuple[int, ...]
    proof: dict[str, Any]

    def __post_init__(self) -> None:
        if not 0.0 <= self.lower <= self.upper <= 1.0:
            raise ValueError("requirement bounds must satisfy 0 <= lower <= upper <= 1")

    @property
    def point(self) -> float:
        return (self.lower + self.upper) / 2


def evaluate_requirement(
    node: RequirementNode,
    context: RequirementContext,
) -> RequirementEvaluation:
    operator = node.operator
    if operator in {
        RequirementOperator.SKILL,
        RequirementOperator.MUST,
        RequirementOperator.SHOULD,
    }:
        value = context.skill(int(node.technology_node_id))
        hard = node.hard or operator == RequirementOperator.MUST
        hard_failed = hard and value.state == EvidenceState.CONFIRMED_MISSING
        lower = value.lower
        if hard and value.state in {
            EvidenceState.UNKNOWN,
            EvidenceState.SELF_CLAIM,
            EvidenceState.TRANSFERABLE,
            EvidenceState.CONTRADICTED,
        }:
            # A hard requirement cannot be safely accepted from an unverified,
            # weak or conflicting claim, although its upper bound stays open.
            lower = 0.0
        unresolved = (
            (int(node.technology_node_id),)
            if lower < value.upper
            else ()
        )
        failed = (int(node.technology_node_id),) if hard_failed else ()
        return RequirementEvaluation(
            lower=lower,
            upper=value.upper,
            hard_failed=hard_failed,
            unresolved_technology_ids=unresolved,
            failed_technology_ids=failed,
            proof=_proof(node, lower, value.upper, hard_failed, [], value.state.value),
        )
    if operator == RequirementOperator.CONSTRAINT:
        value = context.constraint(str(node.constraint_code))
        hard_failed = node.hard and value.state == EvidenceState.CONFIRMED_MISSING
        return RequirementEvaluation(
            lower=value.lower,
            upper=value.upper,
            hard_failed=hard_failed,
            unresolved_technology_ids=(),
            failed_technology_ids=(),
            proof=_proof(node, value.lower, value.upper, hard_failed, [], value.state.value),
        )
    if operator in {
        RequirementOperator.YEARS,
        RequirementOperator.RECENT,
        RequirementOperator.LEVEL,
    }:
        return _evaluate_threshold_leaf(node, context.skill(int(node.technology_node_id)))

    children = [evaluate_requirement(child, context) for child in node.children]
    if operator == RequirementOperator.AND:
        total_weight = sum(child.weight for child in node.children)
        lower = sum(
            child.weight * result.lower
            for child, result in zip(node.children, children, strict=True)
        ) / total_weight
        upper = sum(
            child.weight * result.upper
            for child, result in zip(node.children, children, strict=True)
        ) / total_weight
        hard_failed = any(item.hard_failed for item in children)
    elif operator == RequirementOperator.OR:
        lower = max(item.lower for item in children)
        upper = max(item.upper for item in children)
        hard_failed = node.hard and all(item.upper == 0.0 for item in children)
    elif operator == RequirementOperator.K_OF_N:
        k = int(node.k)
        lower = sum(sorted((item.lower for item in children), reverse=True)[:k]) / k
        upper = sum(sorted((item.upper for item in children), reverse=True)[:k]) / k
        hard_failed = node.hard and sum(item.upper > 0.0 for item in children) < k
    else:  # pragma: no cover - enum exhaustiveness guard
        raise ValueError(f"unsupported requirement operator: {operator.value}")
    unresolved = _unique_ids(
        item
        for child in children
        for item in child.unresolved_technology_ids
    )
    child_failed = _unique_ids(
        item for child in children for item in child.failed_technology_ids
    )
    failed = child_failed if operator == RequirementOperator.AND or hard_failed else ()
    return RequirementEvaluation(
        lower=lower,
        upper=upper,
        hard_failed=hard_failed,
        unresolved_technology_ids=unresolved,
        failed_technology_ids=failed,
        proof=_proof(node, lower, upper, hard_failed, [item.proof for item in children]),
    )


def compile_flat_requirements(
    required: list[tuple[int, float, tuple[str, ...]]],
    *,
    hard_technology_ids: set[int] | None = None,
) -> RequirementNode | None:
    """Compile existing flat required rows into an executable AND(MUST(...)) tree."""
    if not required:
        return None
    hard_ids = hard_technology_ids
    children = tuple(
        RequirementNode(
            operator=(
                RequirementOperator.MUST
                if hard_ids is None or technology_id in hard_ids
                else RequirementOperator.SKILL
            ),
            technology_node_id=technology_id,
            weight=max(float(weight), 0.01),
            hard=hard_ids is None or technology_id in hard_ids,
            evidence_refs=evidence_refs,
        )
        for technology_id, weight, evidence_refs in required
    )
    if len(children) == 1:
        return children[0]
    return RequirementNode(operator=RequirementOperator.AND, children=children)


def _evaluate_threshold_leaf(
    node: RequirementNode,
    value: EvidenceValue,
) -> RequirementEvaluation:
    if value.state == EvidenceState.CONFIRMED_MISSING:
        lower = upper = 0.0
    elif node.operator == RequirementOperator.YEARS:
        required_months = round(float(node.minimum_years) * 12)
        lower = 1.0 if (value.minimum_months or 0) >= required_months else 0.0
        if value.maximum_months is None:
            upper = 1.0
        else:
            upper = 1.0 if value.maximum_months >= required_months else 0.0
    elif node.operator == RequirementOperator.RECENT:
        threshold = int(node.maximum_months)
        lower = (
            1.0
            if value.months_since_last_use_upper is not None
            and value.months_since_last_use_upper <= threshold
            else 0.0
        )
        upper = (
            0.0
            if value.months_since_last_use_lower is not None
            and value.months_since_last_use_lower > threshold
            else 1.0
        )
    else:
        threshold = int(node.minimum_level)
        lower = (
            1.0
            if value.level_lower is not None and value.level_lower >= threshold
            else 0.0
        )
        upper = (
            0.0
            if value.level_upper is not None and value.level_upper < threshold
            else 1.0
        )
    hard_failed = node.hard and upper == 0.0
    technology_id = int(node.technology_node_id)
    unresolved = (technology_id,) if lower < upper else ()
    failed = (technology_id,) if hard_failed else ()
    return RequirementEvaluation(
        lower=lower,
        upper=upper,
        hard_failed=hard_failed,
        unresolved_technology_ids=unresolved,
        failed_technology_ids=failed,
        proof=_proof(node, lower, upper, hard_failed, [], value.state.value),
    )


def _proof(
    node: RequirementNode,
    lower: float,
    upper: float,
    hard_failed: bool,
    children: list[dict[str, Any]],
    evidence_state: str | None = None,
) -> dict[str, Any]:
    proof: dict[str, Any] = {
        "operator": node.operator.value,
        "lower": round(lower, 6),
        "upper": round(upper, 6),
        "hard": node.hard,
        "hard_failed": hard_failed,
    }
    if node.technology_node_id is not None:
        proof["technology_node_id"] = node.technology_node_id
    if node.k is not None:
        proof["k"] = node.k
    if node.minimum_years is not None:
        proof["minimum_years"] = node.minimum_years
    if node.maximum_months is not None:
        proof["maximum_months"] = node.maximum_months
    if node.minimum_level is not None:
        proof["minimum_level"] = node.minimum_level
    if node.constraint_code is not None:
        proof["constraint_code"] = node.constraint_code
    if evidence_state is not None:
        proof["evidence_state"] = evidence_state
    if node.evidence_refs:
        proof["evidence_refs"] = list(node.evidence_refs)
    if children:
        proof["children"] = children
    return proof


def _unique_ids(values) -> tuple[int, ...]:
    return tuple(sorted(set(values)))


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def _optional_string(value: object) -> str | None:
    return None if value is None else str(value)
