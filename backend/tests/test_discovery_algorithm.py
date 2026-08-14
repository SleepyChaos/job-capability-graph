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
    assert result.raw > 0
    assert result.explore == 0.15  # 单条证据仍低于探索地板，不得被地板抬成"有成熟度"
    assert len(result.contributions) == 1


def test_maturity_keeps_resolution_across_the_observed_accumulation_range() -> None:
    """实测语料累积量在 1.3~17.3 之间，这一段必须保持单调且不撞上限。"""

    def _at(count: int) -> float:
        return calculate_maturity(
            [
                MaturityEventSignal(
                    event_id=index,
                    event_type_code="product_release",
                    age_years=0,
                    relevance=1.0,
                    source_quality=0.6,
                )
                for index in range(count)
            ]
        ).raw

    low, mid, high = _at(3), _at(10), _at(35)

    assert low < mid < high
    assert high < 0.98  # 0.98 是硬上限，观测区间内不应触顶
    assert mid - low > 0.1 and high - mid > 0.1


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
