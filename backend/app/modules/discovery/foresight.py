"""前瞻排序与参考窗口：技术方向何时进入岗位需求期。

**这个模块回答什么。** 推演给出的候选是「哪些能力组合正在成形」，不含时间。
本模块补上时间维度：对每个技术方向，用真实里程碑日期重算成熟度轨迹
$M(t)$，找出它跨过岗位化门槛 $\\theta$ 的时点 $t^*$，再叠加一段**传导时滞**
得到参考窗口，最后按窗口起点给出跨域的全局排序。

**为什么落在 L2 而不是 L3。** L3 的成熟度取值重复率 84.3%——绝大多数 L3 没有
自己的里程碑，靠 L2 祖先继承，同一 L2 下的 L3 拿到完全相同的成熟度。在这样的
取值上做前瞻排序会大面积并列，排出来没有意义。L2 是里程碑真正挂载的层级。

**四段里只有第三段是先验。**

| 段 | 来源 |
| --- | --- |
| $M(t)$ 轨迹 | 真实里程碑日期 + 衰减模型，计算得出 |
| $t^*$ 跨过 $\\theta$ 的时点 | 由轨迹计算得出 |
| 传导时滞 | **先验**，见 `experiment_lag_calibration.py` 的截尾标定 |
| 全局排序 | 由前三段推出 |

**措辞约束。** 输出说的是「技术方向 X 预计在 Y 窗口进入岗位需求期」，
不是「该岗位将在 Y 出现」。候选依托多个技术方向，岗位的出现还取决于
这些方向是否真的被同一批雇主组合到一个职位上——那不在本模块的推断范围内。

**$M(t)$ 不单调。** 贡献按 $e^{-\\lambda\\cdot age}$ 衰减，一个方向若长期没有新
里程碑，成熟度会从峰值回落。因此取的是**首次向上穿越**，而不是「当前值 ≥ θ」；
两者在已回落的方向上会给出不同答案，前者才是「何时曾达到门槛」。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from .algorithm import calculate_maturity

# 岗位化门槛。**设定值而非实测值**——曾尝试从横截面标定（成熟度分箱 → 岗位化率），
# 但成熟度与 JD 提及量秩相关 −0.268、84.3% 的 L3 取值重复，数据不足以定出拐点。
# 详见 tools/experiment_jobification_threshold.py。
JOBIFICATION_THRESHOLD = 0.35

# 轨迹采样步长（月）。里程碑本身多为月级精度，再细没有信息量。
TRAJECTORY_STEP_MONTHS = 3


@dataclass(frozen=True)
class DatedEvent:
    """带真实日期的里程碑信号。与 MaturityEventSignal 的区别是保留绝对日期，
    这样才能在任意 as-of 时点重算年龄。"""

    event_id: int
    event_type_code: str
    occurred_on: date
    relevance: float
    source_quality: float


@dataclass(frozen=True)
class ForesightResult:
    technology_code: str
    technology_name: str
    event_count: int
    maturity_now: float
    peak_maturity: float
    crossing_date: date | None
    already_crossed: bool
    window_start: date | None
    window_end: date | None
    trajectory: tuple[tuple[date, float], ...]


def _months_between(earlier: date, later: date) -> int:
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


def _add_months(anchor: date, months: int) -> date:
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    # 只做月级推演，统一落在月中，避免月末日期在不同月份长度下漂移。
    return date(year, month, 15)


def maturity_at(events: list[DatedEvent], as_of: date, *, alpha: float) -> float:
    """重算 as-of 时点的成熟度：只计入当时已发生的事件，年龄相对 as-of 计算。

    这与线上 `_persist_maturity` 用的是同一个 `calculate_maturity`，
    差别只在事件集与年龄的基准点，因此轨迹终点与线上快照一致。
    """
    from .algorithm import MaturityEventSignal

    signals = [
        MaturityEventSignal(
            event_id=event.event_id,
            event_type_code=event.event_type_code,
            age_years=(as_of - event.occurred_on).days / 365.25,
            relevance=event.relevance,
            source_quality=event.source_quality,
        )
        for event in events
        if event.occurred_on <= as_of
    ]
    if not signals:
        return 0.0
    return calculate_maturity(signals, alpha=alpha).raw


def compute_foresight(
    *,
    technology_code: str,
    technology_name: str,
    events: list[DatedEvent],
    as_of: date,
    threshold: float = JOBIFICATION_THRESHOLD,
    lag_months: tuple[int, int] | None = None,
    alpha: float = 0.17,
) -> ForesightResult:
    """算出一个技术方向的成熟度轨迹、跨越时点与参考窗口。

    `lag_months` 为 None 时不给窗口——**没有标定过的时滞就不输出窗口**，
    宁可只给排序，也不要凭空造一个看起来很确定的时间区间。
    """
    if not events:
        return ForesightResult(
            technology_code=technology_code,
            technology_name=technology_name,
            event_count=0,
            maturity_now=0.0,
            peak_maturity=0.0,
            crossing_date=None,
            already_crossed=False,
            window_start=None,
            window_end=None,
            trajectory=(),
        )

    start = min(event.occurred_on for event in events)
    samples: list[tuple[date, float]] = []
    for offset in range(0, _months_between(start, as_of) + 1, TRAJECTORY_STEP_MONTHS):
        moment = _add_months(start, offset)
        if moment > as_of:
            break
        samples.append((moment, maturity_at(events, moment, alpha=alpha)))
    if not samples or samples[-1][0] != as_of:
        samples.append((as_of, maturity_at(events, as_of, alpha=alpha)))

    # 首次向上穿越。在跨越的那一段上做二分细化到月，采样步长本身不应决定精度。
    crossing: date | None = None
    for index in range(1, len(samples)):
        if samples[index - 1][1] < threshold <= samples[index][1]:
            low, high = samples[index - 1][0], samples[index][0]
            while _months_between(low, high) > 1:
                middle = _add_months(low, _months_between(low, high) // 2)
                if maturity_at(events, middle, alpha=alpha) >= threshold:
                    high = middle
                else:
                    low = middle
            crossing = high
            break
    if crossing is None and samples[0][1] >= threshold:
        # 第一个采样点就已达标：证据集中在起点，跨越发生在首个事件当月。
        crossing = samples[0][0]

    window_start = window_end = None
    if crossing is not None and lag_months is not None:
        window_start = _add_months(crossing, lag_months[0])
        window_end = _add_months(crossing, lag_months[1])

    return ForesightResult(
        technology_code=technology_code,
        technology_name=technology_name,
        event_count=len(events),
        maturity_now=samples[-1][1],
        peak_maturity=max(value for _moment, value in samples),
        crossing_date=crossing,
        already_crossed=crossing is not None,
        window_start=window_start,
        window_end=window_end,
        trajectory=tuple(samples),
    )


def rank_foresight(results: list[ForesightResult]) -> list[ForesightResult]:
    """全局前瞻排序：按参考窗口起点，无窗口的按成熟度接近门槛的程度排在其后。

    跨域排序，不按域拆——当前范围已收窄到具身智能领域，再拆过细。
    需要注意其代价：成熟度受里程碑整理密度支配（T1 有 343 条链接、T5 只有 47 条），
    整理投入多的域会系统性地排在前面。这一偏差在报告中显式声明。
    """

    def sort_key(item: ForesightResult) -> tuple:
        if item.window_start is not None:
            return (0, item.window_start.toordinal(), -item.peak_maturity)
        if item.crossing_date is not None:
            return (1, item.crossing_date.toordinal(), -item.peak_maturity)
        # 尚未跨越：离门槛越近排越前。
        return (2, -item.peak_maturity, 0)

    return sorted(results, key=sort_key)


def horizon_label(result: ForesightResult, as_of: date) -> str:
    """给候选卡片用的一句话措辞。主语是技术方向，不是岗位。"""
    if result.crossing_date is None:
        gap = JOBIFICATION_THRESHOLD - result.peak_maturity
        if result.event_count == 0:
            return "无里程碑证据，不作前瞻判断"
        return f"尚未跨过岗位化门槛（峰值成熟度 {result.peak_maturity:.2f}，差 {gap:.2f}）"
    if result.window_start is None:
        return f"已于 {result.crossing_date:%Y-%m} 跨过岗位化门槛（时滞未标定，不给窗口）"
    if result.window_end < as_of:
        return f"参考窗口 {result.window_start:%Y-%m}–{result.window_end:%Y-%m}，已进入需求期"
    return f"预计 {result.window_start:%Y-%m}–{result.window_end:%Y-%m} 进入岗位需求期"


def half_life_years(decay_lambda: float = 0.35) -> float:
    """证据贡献衰减的半衰期，用于解释轨迹为何会回落。"""
    return math.log(2) / decay_lambda
