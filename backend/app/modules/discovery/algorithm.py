import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

POSITIVE_WEIGHTS = {
    "technology_relevance": 0.15,
    "publication_task_gap": 0.22,
    "community_cohesion": 0.12,
    "market_support": 0.14,
    "technology_maturity": 0.10,
    "temporal_growth_stability": 0.10,
    "evidence_completeness": 0.10,
    "novelty": 0.07,
}


EVENT_TYPE_WEIGHTS = {
    "technology_demo": 0.45,
    "paper": 0.55,
    "breakthrough": 0.68,
    "open_source": 0.76,
    "product_release": 0.84,
    "platform_release": 0.88,
    "scaled_deployment": 0.92,
    "enterprise_application": 0.92,
    "standard_policy": 0.72,
    "other": 0.35,
}


@dataclass(frozen=True)
class MaturityEventSignal:
    event_id: int
    event_type_code: str
    age_years: float
    relevance: float
    source_quality: float


@dataclass(frozen=True)
class MaturityContribution:
    event_id: int
    type_weight: float
    relevance: float
    recency: float
    source_quality: float
    contribution: float


@dataclass(frozen=True)
class MaturityResult:
    raw: float
    explore: float
    contributions: tuple[MaturityContribution, ...]


@dataclass(frozen=True)
class CandidateSignals:
    technology_relevance: float
    publication_task_gap: float
    community_cohesion: float
    market_support: float
    technology_maturity: float
    temporal_growth_stability: float
    evidence_completeness: float
    novelty: float
    job_count: int
    organization_count: int
    source_count: int
    observation_window_count: int
    application_evidence_count: int
    unverified_technology: bool = False
    marketing_only: bool = False
    contradiction: bool = False


@dataclass(frozen=True)
class ScoreComponent:
    code: str
    component_type: str
    raw_score: float
    weight: float
    weighted_score: float


@dataclass(frozen=True)
class CandidateScore:
    score: float
    maturity_stage: str
    components: tuple[ScoreComponent, ...]
    risk_flags: tuple[str, ...]


def calculate_maturity(
    events: list[MaturityEventSignal],
    *,
    alpha: float = 0.17,
    decay_lambda: float = 0.35,
    exploration_floor: float = 0.15,
) -> MaturityResult:
    """按证据累积量计算技术成熟度。

    alpha 决定饱和速度。实测语料的累积量分布在 1.3~17.3 之间，早期取值 0.85 会让
    累积量超过 5 的技术全部压到 0.98 上限（15 个有证据节点里 8 个并列），成熟度这一维
    失去区分度。0.17 使该区间映射到约 0.20~0.95，上限不再是绑定约束。
    """
    contributions = []
    total = 0.0
    for event in events:
        type_weight = EVENT_TYPE_WEIGHTS.get(event.event_type_code, EVENT_TYPE_WEIGHTS["other"])
        recency = math.exp(-decay_lambda * max(0.0, event.age_years))
        relevance = clamp01(event.relevance)
        source_quality = clamp01(event.source_quality)
        contribution = type_weight * relevance * recency * source_quality
        total += contribution
        contributions.append(
            MaturityContribution(
                event_id=event.event_id,
                type_weight=type_weight,
                relevance=relevance,
                recency=recency,
                source_quality=source_quality,
                contribution=contribution,
            )
        )
    raw = min(0.98, 1 - math.exp(-alpha * total)) if total else 0.0
    return MaturityResult(
        raw=raw,
        explore=max(exploration_floor, raw),
        contributions=tuple(sorted(contributions, key=lambda item: -item.contribution)),
    )


def calculate_market_support(
    *,
    job_count: int,
    organization_count: int,
    source_count: int,
    observation_window_count: int,
    application_evidence_count: int,
) -> float:
    jd_support = saturating(job_count, 8)
    cross_company = saturating(organization_count, 5)
    cross_source = saturating(source_count, 3)
    temporal = saturating(observation_window_count, 3)
    application = saturating(application_evidence_count, 3)
    return (
        0.35 * jd_support
        + 0.25 * cross_company
        + 0.10 * cross_source
        + 0.15 * temporal
        + 0.15 * application
    )


def calculate_task_gap(
    *,
    technology_relevance: float,
    maturity: float,
    existing_role_coverage: float,
    evidence_strength: float,
    organization_count: int,
    market_support: float,
) -> float:
    cross_company = saturating(organization_count, 5)
    return (
        clamp01(technology_relevance)
        * clamp01(maturity)
        * (1 - clamp01(existing_role_coverage))
        * clamp01(evidence_strength)
        * (0.55 + 0.45 * cross_company)
        * clamp01(market_support)
    )


def score_candidate(signals: CandidateSignals) -> CandidateScore:
    values = {name: clamp01(getattr(signals, name)) for name in POSITIVE_WEIGHTS}
    components = [
        ScoreComponent(name, "positive", value, POSITIVE_WEIGHTS[name], value * weight)
        for name, weight in POSITIVE_WEIGHTS.items()
        for value in [values[name]]
    ]
    penalties = {
        "single_company_penalty": 0.10 if signals.organization_count < 2 else 0.0,
        "single_source_penalty": 0.05 if signals.source_count < 2 else 0.0,
        "marketing_penalty": 0.15 if signals.marketing_only else 0.0,
        "contradiction_penalty": 0.12 if signals.contradiction else 0.0,
        "unverified_technology_penalty": 0.20 if signals.unverified_technology else 0.0,
    }
    components.extend(
        ScoreComponent(code, "penalty", value, 1.0, -value)
        for code, value in penalties.items()
        if value
    )
    score = clamp01(sum(item.weighted_score for item in components)) * 100
    risks = []
    if signals.job_count < 3:
        risks.append("insufficient_job_evidence")
    if signals.organization_count < 2:
        risks.append("single_company_signal")
    if signals.source_count < 2:
        risks.append("single_source_signal")
    if signals.observation_window_count < 2:
        risks.append("insufficient_temporal_history")
    if signals.application_evidence_count < 1:
        risks.append("missing_application_evidence")
    if signals.unverified_technology:
        risks.append("unverified_technology")
    if signals.marketing_only:
        risks.append("marketing_only")

    # Maturity stage is evidence-gated, independently of the review workflow.
    stage = "potential"
    if (
        score >= 45
        and signals.job_count >= 3
        and signals.organization_count >= 2
        and signals.observation_window_count >= 2
        and not signals.unverified_technology
    ):
        stage = "budding"
    if (
        score >= 65
        and signals.source_count >= 2
        and signals.application_evidence_count >= 1
        and signals.technology_maturity >= 0.35
        and signals.publication_task_gap >= 0.25
        and signals.observation_window_count >= 3
    ):
        stage = "emerging"
    return CandidateScore(
        score=float(Decimal(str(score)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        maturity_stage=stage,
        components=tuple(components),
        risk_flags=tuple(risks),
    )


def saturating(value: int, target: int) -> float:
    return clamp01(value / target) if target else 0.0


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
