"""前瞻计算的单元测试。

重点覆盖两处容易出错的地方：**M(t) 不单调**（贡献按 exp(-λ·age) 衰减，
长期无新里程碑的方向会从峰值回落），以及**跨越时点必须是首次向上穿越**
而不是「当前值 ≥ θ」——两者在已回落的方向上给出不同答案。
"""

from datetime import date

from app.modules.discovery.foresight import (
    DatedEvent,
    compute_foresight,
    horizon_label,
    rank_foresight,
)


def event(event_id: int, year: int, month: int = 1) -> DatedEvent:
    return DatedEvent(
        event_id=event_id,
        event_type_code="paper",
        occurred_on=date(year, month, 1),
        relevance=1.0,
        source_quality=1.0,
    )


def test_no_events_yields_no_crossing():
    result = compute_foresight(
        technology_code="T1.01",
        technology_name="示例",
        events=[],
        as_of=date(2026, 8, 31),
    )
    assert result.crossing_date is None
    assert result.event_count == 0
    assert horizon_label(result, date(2026, 8, 31)) == "无里程碑证据，不作前瞻判断"


def test_crossing_is_detected_and_precedes_as_of():
    events = [event(index, 2024, 1 + index % 12) for index in range(20)]
    result = compute_foresight(
        technology_code="T1.01",
        technology_name="示例",
        events=events,
        as_of=date(2026, 8, 31),
    )
    assert result.crossing_date is not None
    assert result.crossing_date <= date(2026, 8, 31)
    assert result.peak_maturity >= 0.35


def test_maturity_falls_back_after_evidence_ages():
    """一批陈旧里程碑：峰值曾越过门槛，当前值已回落到门槛之下。

    这正是必须取「首次向上穿越」的理由——按当前值判断会说它从未达标。
    """
    events = [event(index, 2016, 1 + index % 12) for index in range(30)]
    result = compute_foresight(
        technology_code="T1.01",
        technology_name="陈旧方向",
        events=events,
        as_of=date(2026, 8, 31),
    )
    assert result.peak_maturity > result.maturity_now
    assert result.peak_maturity >= 0.35
    assert result.maturity_now < 0.35
    assert result.crossing_date is not None
    assert result.crossing_date.year <= 2018


def test_no_window_without_lag_prior():
    """时滞未标定时必须不给窗口，宁可只给排序。"""
    events = [event(index, 2024) for index in range(20)]
    result = compute_foresight(
        technology_code="T1.01",
        technology_name="示例",
        events=events,
        as_of=date(2026, 8, 31),
    )
    assert result.window_start is None and result.window_end is None
    assert "不给窗口" in horizon_label(result, date(2026, 8, 31))


def test_ranking_puts_crossed_before_pending():
    crossed = compute_foresight(
        technology_code="T1.01",
        technology_name="已跨过",
        events=[event(index, 2024) for index in range(20)],
        as_of=date(2026, 8, 31),
    )
    pending = compute_foresight(
        technology_code="T2.01",
        technology_name="未跨过",
        events=[event(100, 2024)],
        as_of=date(2026, 8, 31),
    )
    assert pending.crossing_date is None
    assert [item.technology_code for item in rank_foresight([pending, crossed])] == [
        "T1.01",
        "T2.01",
    ]
