"""Deterministic evidence states used by person-job matching.

The LLM may propose facts, but only this module assigns score bounds and allows
state transitions.  Keeping these rules pure makes them replayable and easy to
test independently from database and model availability.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum


class EvidenceState(StrEnum):
    UNKNOWN = "unknown"
    SELF_CLAIM = "self_claim"
    CONTEXTUAL = "contextual"
    VERIFIED = "verified"
    TRANSFERABLE = "transferable"
    CONTRADICTED = "contradicted"
    CONFIRMED_MISSING = "confirmed_missing"


STATE_BOUNDS: dict[EvidenceState, tuple[float, float]] = {
    EvidenceState.UNKNOWN: (0.0, 1.0),
    EvidenceState.SELF_CLAIM: (0.20, 1.0),
    EvidenceState.CONTEXTUAL: (0.65, 1.0),
    EvidenceState.VERIFIED: (1.0, 1.0),
    EvidenceState.TRANSFERABLE: (0.15, 0.65),
    EvidenceState.CONTRADICTED: (0.0, 0.25),
    EvidenceState.CONFIRMED_MISSING: (0.0, 0.0),
}


ALLOWED_TRANSITIONS: dict[EvidenceState, frozenset[EvidenceState]] = {
    EvidenceState.UNKNOWN: frozenset(
        {
            EvidenceState.SELF_CLAIM,
            EvidenceState.CONTEXTUAL,
            EvidenceState.VERIFIED,
            EvidenceState.TRANSFERABLE,
            EvidenceState.CONTRADICTED,
            EvidenceState.CONFIRMED_MISSING,
        }
    ),
    EvidenceState.SELF_CLAIM: frozenset(
        {
            EvidenceState.CONTEXTUAL,
            EvidenceState.VERIFIED,
            EvidenceState.CONTRADICTED,
            EvidenceState.CONFIRMED_MISSING,
        }
    ),
    EvidenceState.CONTEXTUAL: frozenset(
        {
            EvidenceState.VERIFIED,
            EvidenceState.CONTRADICTED,
            EvidenceState.CONFIRMED_MISSING,
        }
    ),
    EvidenceState.VERIFIED: frozenset({EvidenceState.CONTRADICTED}),
    EvidenceState.TRANSFERABLE: frozenset(
        {
            EvidenceState.SELF_CLAIM,
            EvidenceState.CONTEXTUAL,
            EvidenceState.VERIFIED,
            EvidenceState.CONTRADICTED,
            EvidenceState.CONFIRMED_MISSING,
        }
    ),
    EvidenceState.CONTRADICTED: frozenset({EvidenceState.VERIFIED}),
    EvidenceState.CONFIRMED_MISSING: frozenset({EvidenceState.VERIFIED}),
}


class InvalidEvidenceTransition(ValueError):
    """Raised when an evidence state change would bypass required verification."""


@dataclass(frozen=True)
class EvidenceValue:
    state: EvidenceState
    lower: float
    upper: float
    minimum_months: int | None = None
    maximum_months: int | None = None
    months_since_last_use_lower: int | None = None
    months_since_last_use_upper: int | None = None
    level_lower: int | None = None
    level_upper: int | None = None
    source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.lower <= self.upper <= 1.0:
            raise ValueError("evidence bounds must satisfy 0 <= lower <= upper <= 1")
        if (
            self.minimum_months is not None
            and self.maximum_months is not None
            and self.minimum_months > self.maximum_months
        ):
            raise ValueError("minimum_months cannot exceed maximum_months")
        if (
            self.months_since_last_use_lower is not None
            and self.months_since_last_use_upper is not None
            and self.months_since_last_use_lower > self.months_since_last_use_upper
        ):
            raise ValueError(
                "months_since_last_use_lower cannot exceed months_since_last_use_upper"
            )
        if (
            self.level_lower is not None
            and self.level_upper is not None
            and self.level_lower > self.level_upper
        ):
            raise ValueError("level_lower cannot exceed level_upper")

    @classmethod
    def for_state(
        cls,
        state: EvidenceState | str,
        *,
        lower: float | None = None,
        upper: float | None = None,
        minimum_months: int | None = None,
        maximum_months: int | None = None,
        months_since_last_use_lower: int | None = None,
        months_since_last_use_upper: int | None = None,
        level_lower: int | None = None,
        level_upper: int | None = None,
        source_ids: tuple[str, ...] = (),
    ) -> EvidenceValue:
        normalized_state = EvidenceState(state)
        default_lower, default_upper = STATE_BOUNDS[normalized_state]
        return cls(
            state=normalized_state,
            lower=default_lower if lower is None else lower,
            upper=default_upper if upper is None else upper,
            minimum_months=minimum_months,
            maximum_months=maximum_months,
            months_since_last_use_lower=months_since_last_use_lower,
            months_since_last_use_upper=months_since_last_use_upper,
            level_lower=level_lower,
            level_upper=level_upper,
            source_ids=source_ids,
        )

    @property
    def point(self) -> float:
        return (self.lower + self.upper) / 2


def transition_evidence(
    current: EvidenceValue,
    target_state: EvidenceState | str,
    *,
    verification_present: bool = False,
    source_ids: tuple[str, ...] = (),
) -> EvidenceValue:
    """Move evidence to a legal state while preserving its audit references."""
    target = EvidenceState(target_state)
    if target == current.state:
        merged_sources = tuple(dict.fromkeys((*current.source_ids, *source_ids)))
        return replace(current, source_ids=merged_sources)
    if target not in ALLOWED_TRANSITIONS[current.state]:
        raise InvalidEvidenceTransition(
            f"illegal evidence transition: {current.state.value} -> {target.value}"
        )
    if target == EvidenceState.VERIFIED and not verification_present:
        raise InvalidEvidenceTransition("verified state requires verification evidence")
    lower, upper = STATE_BOUNDS[target]
    return replace(
        current,
        state=target,
        lower=lower,
        upper=upper,
        source_ids=tuple(dict.fromkeys((*current.source_ids, *source_ids))),
    )


def interval_is_refinement(previous: EvidenceValue, current: EvidenceValue) -> bool:
    """Return whether the newer evidence removes possibilities without widening them."""
    return current.lower >= previous.lower and current.upper <= previous.upper
