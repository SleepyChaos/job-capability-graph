from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.ingestion.models import primary_key_type

# technology_node_id 为 0 表示该行为技术域聚合行（跨技术去重），非 0 表示单技术行。
DOMAIN_AGGREGATE_TECHNOLOGY_ID = 0


class TechnologyDailyTriggerMetric(Base):
    """按日技术触发指标（后端设计 §11.4）。

    trigger_document_count 按"文档×技术×日"去重；域聚合行按域内全部技术去重。
    """

    __tablename__ = "biz_technology_daily_trigger_metric"

    technology_daily_trigger_metric_id: Mapped[int] = mapped_column(
        primary_key_type, primary_key=True
    )
    metric_date: Mapped[date] = mapped_column(Date)
    technology_domain_code: Mapped[str] = mapped_column(String(8))
    technology_node_id: Mapped[int] = mapped_column(Integer, default=0)
    trigger_document_count: Mapped[int] = mapped_column(Integer, default=0)
    trigger_mention_count: Mapped[int] = mapped_column(Integer, default=0)
    independent_org_count: Mapped[int] = mapped_column(Integer, default=0)
    independent_source_count: Mapped[int] = mapped_column(Integer, default=0)
    clustering_run_code: Mapped[str] = mapped_column(String(64))
    calculation_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "metric_date",
            "technology_domain_code",
            "technology_node_id",
            "clustering_run_code",
            name="uk_daily_trigger_metric",
        ),
    )


TRIPLE_SUBJECT_KINDS = {"organization", "cluster", "technology"}
TRIPLE_PREDICATES = {
    "org_has_tech",
    "cluster_needs_tech",
    "org_has_cluster",
    "hierarchy",
    "dg_membership",
}
PLAUSIBILITY_LEVELS = {"low", "medium", "high", "auto_suppressed"}


class TripleContradictionAssessment(Base):
    """Layer C: 三元组 plausibility 打分 + 矛盾审计留痕（对应设计 RC-03）。

    抽样 top-200~2000 子图计算 embedding/path/rule 综合 plausibility；低分
    (plausibility_level='low') 代表潜在矛盾/幻觉边，进入人工复核队列。
    """

    __tablename__ = "biz_triple_contradiction_assessment"

    triple_contradiction_assessment_id: Mapped[int] = mapped_column(
        primary_key_type, primary_key=True
    )
    audit_run_code: Mapped[str] = mapped_column(String(64), index=True)
    audit_model: Mapped[str] = mapped_column(
        String(32), default="composite_v1"
    )  # composite_v1 | pykeen_transe | pykeen_complex
    sample_scope: Mapped[str] = mapped_column(
        String(16), default="top_200"
    )  # top_200 | top_2000 | full

    subject_kind: Mapped[str] = mapped_column(String(24))  # organization|cluster|technology
    subject_id: Mapped[str] = mapped_column(
        String(64), index=True
    )  # org_code | cluster_code | tech_code
    subject_label: Mapped[str] = mapped_column(String(255), default="")
    predicate: Mapped[str] = mapped_column(String(32))  # org_has_tech | cluster_needs_tech | ...
    object_kind: Mapped[str] = mapped_column(String(24))
    object_id: Mapped[str] = mapped_column(String(64), index=True)
    object_label: Mapped[str] = mapped_column(String(255), default="")

    plausibility_score: Mapped[float] = mapped_column(Numeric(5, 4), index=True)  # 0.0~1.0
    plausibility_level: Mapped[str] = mapped_column(
        String(16), index=True
    )  # low/medium/high/auto_suppressed
    rule_flags: Mapped[dict] = mapped_column(
        JSON, default=dict
    )  # {cooccur: 0.3, external_agree: 0.7, taxon_violation: True}
    component_scores: Mapped[dict] = mapped_column(
        JSON, default=dict
    )  # {pykeen: 0.2, path_count: 0.4, support: 0.5}
    review_status_code: Mapped[str] = mapped_column(
        String(24), default="pending_review", index=True
    )  # pending_review | accepted_as_true | false_positive_edge | redirected_edge
    reviewer_code: Mapped[str | None] = mapped_column(String(64))
    review_note_text: Mapped[str | None] = mapped_column(Text)
    evidence_summary_json: Mapped[dict] = mapped_column(
        JSON, default=dict
    )  # supporting_job_count, org_count, etc.
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint(
            "audit_run_code",
            "subject_id",
            "predicate",
            "object_id",
            name="uk_triple_audit_key",
        ),
    )
