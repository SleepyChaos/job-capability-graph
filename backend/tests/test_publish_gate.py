from app.modules.extraction.publish_gate import (
    AUTO_PUBLISH_THRESHOLD,
    COMPONENT_WEIGHTS,
    MANUAL_REVIEW_THRESHOLD,
    compute_publish_score,
    route_publish_score,
)

HIGH_COMPONENTS = {
    "source_reliability": 95,
    "extraction_confidence": 95,
    "schema_completeness": 100,
    "evidence_coverage": 100,
    "cross_source_support": 80,
    "timeliness": 90,
    "consistency": 100,
}


def test_publish_score_uses_design_weights() -> None:
    full = {code: 100.0 for code in COMPONENT_WEIGHTS}
    assert compute_publish_score(full) == 100.0
    zeroed = dict(full)
    zeroed["source_reliability"] = 0.0
    assert compute_publish_score(zeroed) == 100.0 - 0.22 * 100


def test_penalties_reduce_score() -> None:
    base = compute_publish_score(HIGH_COMPONENTS)
    penalized = compute_publish_score(
        HIGH_COMPONENTS,
        {"duplicate_penalty": 5, "contradiction_penalty": 3, "hallucination_penalty": 2},
    )
    assert penalized == base - 10


def test_routing_hits_three_paths() -> None:
    high = compute_publish_score(HIGH_COMPONENTS)
    assert high >= AUTO_PUBLISH_THRESHOLD
    assert route_publish_score(high) == "auto_publish"

    mid_components = dict(HIGH_COMPONENTS)
    mid_components["cross_source_support"] = 0
    mid_components["timeliness"] = 60
    mid = compute_publish_score(mid_components)
    assert MANUAL_REVIEW_THRESHOLD <= mid < AUTO_PUBLISH_THRESHOLD
    assert route_publish_score(mid) == "manual_review"

    low_components = dict(HIGH_COMPONENTS)
    low_components["source_reliability"] = 20
    low_components["cross_source_support"] = 0
    low_components["timeliness"] = 20
    low = compute_publish_score(low_components)
    assert low < MANUAL_REVIEW_THRESHOLD
    assert route_publish_score(low) == "rejected"


def test_high_impact_always_requires_review_and_hard_error_rejects() -> None:
    high = compute_publish_score(HIGH_COMPONENTS)
    assert route_publish_score(high, high_impact=True) == "manual_review"
    assert route_publish_score(high, hard_error=True) == "rejected"
