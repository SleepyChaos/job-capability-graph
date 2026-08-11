from app.modules.discovery.algorithm import (
    CandidateSignals,
    MaturityEventSignal,
    calculate_maturity,
    score_candidate,
)


def test_maturity_uses_verified_event_contributions_without_artificial_raw_floor() -> None:
    empty = calculate_maturity([])
    result = calculate_maturity(
        [
            MaturityEventSignal(
                event_id=1,
                event_type_code="scaled_deployment",
                age_years=0,
                relevance=0.9,
                source_quality=0.8,
            )
        ]
    )

    assert empty.raw == 0
    assert empty.explore == 0.15
    assert result.raw > 0.4
    assert len(result.contributions) == 1


def test_candidate_stage_is_evidence_gated_independently_of_score() -> None:
    weak = score_candidate(_signals(organization_count=1, observation_window_count=1))
    strong = score_candidate(_signals())

    assert weak.maturity_stage == "potential"
    assert "single_company_signal" in weak.risk_flags
    assert strong.maturity_stage == "emerging"
    assert strong.score > weak.score


def _signals(**overrides) -> CandidateSignals:
    values = {
        "technology_relevance": 0.95,
        "publication_task_gap": 0.8,
        "community_cohesion": 0.85,
        "market_support": 0.85,
        "technology_maturity": 0.8,
        "temporal_growth_stability": 0.9,
        "evidence_completeness": 0.9,
        "novelty": 0.9,
        "job_count": 8,
        "organization_count": 5,
        "source_count": 3,
        "observation_window_count": 3,
        "application_evidence_count": 2,
    }
    values.update(overrides)
    return CandidateSignals(**values)
