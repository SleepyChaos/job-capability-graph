import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# 正向维度与权重。权重和为 1，评分 = 加权和减去惩罚项后乘 100。
#
# **technology_relevance 已移除。** 它曾占 0.15，取值恒为 1.0——词表本身就限定在
# 具身智能域内，候选的技术按构造必然「域内相关」，这一维在当前设计下是空转的，
# 给每个候选加同样的常数，不产生任何区分度却占着权重表 15% 的篇幅。原权重按比例
# 摊回其余七维（各自除以 0.85），因此维度之间的相对关系不变。
#
# **temporal_growth_stability 保留但当前无区分度。** 227 个候选里 226 个取到 1.0，
# 因为观测窗 2/3 是合成日期。与上一条不同，它不是设计空转而是数据所限——JD 侧有了
# 真实跨月采集之后它会重新变得有意义，所以留在表里而不是删掉。
POSITIVE_WEIGHTS = {
    "publication_task_gap": 0.26,
    "market_support": 0.16,
    "community_cohesion": 0.14,
    "technology_maturity": 0.12,
    "temporal_growth_stability": 0.12,
    "evidence_completeness": 0.12,
    "novelty": 0.08,
}


EVENT_TYPE_WEIGHTS = {
    "technology_demo": 0.45,
    "paper": 0.55,
    # 专利在研发完成后、产品上市前申请，可证明技术可实现但不证明已部署，
    # 因此高于论文、低于工程突破。注意专利自申请到公开有约 18 个月审查期，
    # 采集到的 event_date 若取公开日会系统性晚于真实突破时点。
    "patent": 0.60,
    "breakthrough": 0.68,
    # 融资反映资本对商业化前景的判断，是技术突破与产品发布之间的中介信号，
    # 对岗位涌现有较强前瞻性（融资完成后通常 3—6 个月开始批量招聘），
    # 但其本身不构成技术成熟度证据，故低于产品发布。
    "funding": 0.70,
    "standard_policy": 0.72,
    "open_source": 0.76,
    "product_release": 0.84,
    "platform_release": 0.88,
    "scaled_deployment": 0.92,
    "enterprise_application": 0.92,
    "other": 0.35,
}

# 技术域 → 技术类型。三类技术的工程化路径不同，传导节奏差异显著。
DOMAIN_TECHNOLOGY_CLASS = {
    "T1": "algorithm",  # 智能算法与模型
    "T2": "hardware",  # 感知与传感
    "T3": "hardware",  # 本体与核心零部件
    "T4": "algorithm",  # 数据与仿真
    "T5": "system_integration",  # 系统软件与工具链
    "T6": "system_integration",  # 交互安全与评测标准
    "T7": "system_integration",  # 应用与场景
}

# 各技术类型的传导时滞基线区间（月）与修正系数。
# 基线取自外部参考研究的实测区间，属于先验参数而非本项目观测结果；
# 本项目 JD 侧尚不具备跨月真实时间序列，无法自行估计，故标记为 reference_prior。
# 待多月真实采集到位后应改由数据估计，并保留此处作为对照基线。
TECHNOLOGY_CLASS_LAG_PRIOR = {
    "algorithm": {"low_months": 10, "high_months": 15, "coefficient": 0.8},
    "system_integration": {"low_months": 12, "high_months": 18, "coefficient": 1.0},
    "hardware": {"low_months": 15, "high_months": 24, "coefficient": 1.3},
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
    maturity: float,
    existing_role_coverage: float,
    evidence_strength: float,
    organization_count: int,
    market_support: float,
) -> float:
    # technology_relevance 曾作为一个乘性因子出现在这里，取值恒为 1.0（域内词表，
    # 见 POSITIVE_WEIGHTS 上方说明），是个不做事的乘 1，一并去掉。
    cross_company = saturating(organization_count, 5)
    return (
        clamp01(maturity)
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


def estimate_transmission_lag(
    domain_codes: tuple[str, ...],
    *,
    class_prior: dict | None = None,
    domain_class_map: dict | None = None,
) -> dict:
    """按技术域构成估计"技术突破 → 岗位需求涌现"的传导时滞区间（月）。

    这是**先验估计**而非本项目的观测结果：JD 侧目前没有跨月真实采集，
    无法从数据估计时滞。输出用于前瞻标注与后续回测对照，不得当作实测值引用。

    多技术组合按各自类型的区间取并集后再乘以加权修正系数——组合中只要含硬件类，
    整体工程化节奏就会被最慢的一环拖住，因此上界取各类型的最大值。
    """
    prior = class_prior or TECHNOLOGY_CLASS_LAG_PRIOR
    mapping = domain_class_map or DOMAIN_TECHNOLOGY_CLASS
    classes = [mapping[code] for code in domain_codes if code in mapping]
    if not classes:
        return {
            "status": "unknown_domain",
            "technology_classes": [],
            "low_months": None,
            "high_months": None,
            "coefficient": None,
        }
    counts = {item: classes.count(item) for item in set(classes)}
    total = sum(counts.values())
    coefficient = sum(prior[item]["coefficient"] * n for item, n in counts.items()) / total
    low = min(prior[item]["low_months"] for item in counts)
    high = max(prior[item]["high_months"] for item in counts)
    return {
        "status": "reference_prior",
        "technology_classes": sorted(counts),
        "low_months": round(low * coefficient, 1),
        "high_months": round(high * coefficient, 1),
        "coefficient": round(coefficient, 3),
    }


def saturating(value: int, target: int) -> float:
    return clamp01(value / target) if target else 0.0


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
