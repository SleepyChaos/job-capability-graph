"""统一发布分数与分流规则（后端设计 §6.3）。

publish_score =
  0.22 × source_reliability
+ 0.18 × extraction_confidence
+ 0.16 × schema_completeness
+ 0.14 × evidence_coverage
+ 0.12 × cross_source_support
+ 0.10 × timeliness
+ 0.08 × consistency
- duplicate_penalty
- contradiction_penalty
- hallucination_penalty

分流：
- score >= 85 且无硬错误 → auto_publish；
- 65 <= score < 85 → manual_review；
- score < 65 或存在硬错误 → rejected；
- 高影响对象（里程碑、新标准技术词、新岗位定义）即使高分也必须人工审批。

所有分量为 0–100；权重与阈值如需调整，必须同步修改 PUBLISH_GATE_VERSION。
"""

from __future__ import annotations

PUBLISH_GATE_VERSION = "publish_gate_v1"

COMPONENT_WEIGHTS = {
    "source_reliability": 0.22,
    "extraction_confidence": 0.18,
    "schema_completeness": 0.16,
    "evidence_coverage": 0.14,
    "cross_source_support": 0.12,
    "timeliness": 0.10,
    "consistency": 0.08,
}

PENALTY_CODES = ("duplicate_penalty", "contradiction_penalty", "hallucination_penalty")

AUTO_PUBLISH_THRESHOLD = 85.0
MANUAL_REVIEW_THRESHOLD = 65.0

HIGH_IMPACT_REVIEW_ROUTE = "manual_review"


def clamp_component(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def compute_publish_score(
    components: dict[str, float], penalties: dict[str, float] | None = None
) -> float:
    """按设计公式计算发布分数；缺失分量按 0 计，惩罚项缺省为 0。"""
    score = sum(
        COMPONENT_WEIGHTS[code] * clamp_component(components.get(code, 0.0))
        for code in COMPONENT_WEIGHTS
    )
    for code in PENALTY_CODES:
        score -= clamp_component((penalties or {}).get(code, 0.0))
    return round(max(0.0, min(100.0, score)), 2)


def route_publish_score(
    score: float, *, hard_error: bool = False, high_impact: bool = False
) -> str:
    """返回 auto_publish / manual_review / rejected 三态分流结论。"""
    if hard_error or score < MANUAL_REVIEW_THRESHOLD:
        return "rejected"
    if high_impact:
        return HIGH_IMPACT_REVIEW_ROUTE
    if score >= AUTO_PUBLISH_THRESHOLD:
        return "auto_publish"
    return "manual_review"
