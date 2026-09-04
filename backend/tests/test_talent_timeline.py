from datetime import date

import pytest

from app.modules.talent.service import (
    _evidence_timeline_bounds,
    _recency_score_bounds,
)


def test_exact_month_range_produces_reproducible_duration_and_recency() -> None:
    reference_date = date(2026, 8, 20)

    timeline = _evidence_timeline_bounds(
        "项目周期：2024.03—2026.06，负责模型部署。",
        reference_date,
    )

    assert timeline == (28, 28, 2, 2)
    assert _recency_score_bounds(
        "项目周期：2024.03—2026.06，负责模型部署。",
        reference_date,
    ) == pytest.approx((1 - 2 / 60, 1 - 2 / 60))


def test_year_only_range_preserves_date_uncertainty() -> None:
    timeline = _evidence_timeline_bounds(
        "2024年至2025年参与平台建设",
        date(2026, 8, 20),
    )

    assert timeline == (2, 24, 8, 19)


def test_ongoing_marker_is_current_but_does_not_invent_duration() -> None:
    timeline = _evidence_timeline_bounds(
        "目前持续使用 Python",
        date(2026, 8, 20),
    )

    assert timeline == (None, None, 0, 0)


def test_no_date_keeps_recency_unknown() -> None:
    assert _recency_score_bounds("熟悉 Python", date(2026, 8, 20)) is None
