from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.ingestion.models import primary_key_type


class DiscoveryRun(Base):
    __tablename__ = "biz_role_discovery_run"

    discovery_run_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    run_code: Mapped[str] = mapped_column(String(64), unique=True)
    mode_code: Mapped[str] = mapped_column(String(32))
    target_date: Mapped[date] = mapped_column(Date)
    window_start_date: Mapped[date | None] = mapped_column(Date)
    clustering_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("biz_job_clustering_run.clustering_run_id")
    )
    taxonomy_version_id: Mapped[int] = mapped_column(
        ForeignKey("md_technology_taxonomy_version.taxonomy_version_id")
    )
    selected_technology_ids_json: Mapped[list | None] = mapped_column(JSON)
    query_role_name: Mapped[str | None] = mapped_column(String(500))
    query_description: Mapped[str | None] = mapped_column(Text)
    algorithm_version: Mapped[str] = mapped_column(String(64))
    parameter_json: Mapped[dict] = mapped_column(JSON)
    input_snapshot_json: Mapped[dict] = mapped_column(JSON)
    input_snapshot_hash: Mapped[str] = mapped_column(String(64))
    result_summary_json: Mapped[dict | None] = mapped_column(JSON)
    run_status_code: Mapped[str] = mapped_column(String(32), default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "mode_code", "algorithm_version", "input_snapshot_hash", name="uk_discovery_input"
        ),
        Index("idx_discovery_run_mode_status", "mode_code", "run_status_code", "target_date"),
    )


class TechnologyMaturitySnapshot(Base):
    __tablename__ = "biz_technology_maturity_snapshot"

    maturity_snapshot_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    discovery_run_id: Mapped[int] = mapped_column(
        ForeignKey("biz_role_discovery_run.discovery_run_id")
    )
    technology_node_id: Mapped[int] = mapped_column(
        ForeignKey("md_technology_node.technology_node_id")
    )
    maturity_raw_score: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    maturity_explore_score: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    verified_event_count: Mapped[int] = mapped_column(Integer, default=0)
    evidence_status_code: Mapped[str] = mapped_column(String(32))

    __table_args__ = (
        UniqueConstraint("discovery_run_id", "technology_node_id", name="uk_maturity_run_tech"),
    )


class MaturityEventContribution(Base):
    __tablename__ = "rel_maturity_event_contribution"

    maturity_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("biz_technology_maturity_snapshot.maturity_snapshot_id"), primary_key=True
    )
    milestone_event_id: Mapped[int] = mapped_column(
        ForeignKey("biz_milestone_event.milestone_event_id"), primary_key=True
    )
    type_weight: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    relevance_score: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    recency_score: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    source_quality_score: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    contribution_score: Mapped[Decimal] = mapped_column(Numeric(7, 6))


class IndustryTask(Base):
    __tablename__ = "biz_industry_task_candidate"

    industry_task_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    discovery_run_id: Mapped[int] = mapped_column(
        ForeignKey("biz_role_discovery_run.discovery_run_id")
    )
    task_code: Mapped[str] = mapped_column(String(64))
    task_name: Mapped[str] = mapped_column(String(500))
    normalized_task_text: Mapped[str] = mapped_column(Text)
    action_verb: Mapped[str | None] = mapped_column(String(100))
    task_object: Mapped[str | None] = mapped_column(String(500))
    expected_output: Mapped[str | None] = mapped_column(String(500))
    evidence_strength_score: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    market_support_score: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    existing_role_coverage_score: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    task_gap_score: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    job_count: Mapped[int] = mapped_column(Integer, default=0)
    organization_count: Mapped[int] = mapped_column(Integer, default=0)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    evidence_status_code: Mapped[str] = mapped_column(String(32))

    __table_args__ = (
        UniqueConstraint("discovery_run_id", "task_code", name="uk_discovery_task_code"),
        Index("idx_discovery_task_gap", "discovery_run_id", "task_gap_score"),
    )


class IndustryTaskTechnology(Base):
    __tablename__ = "rel_industry_task_technology"

    industry_task_id: Mapped[int] = mapped_column(
        ForeignKey("biz_industry_task_candidate.industry_task_id"), primary_key=True
    )
    technology_node_id: Mapped[int] = mapped_column(
        ForeignKey("md_technology_node.technology_node_id"), primary_key=True
    )
    relation_type_code: Mapped[str] = mapped_column(String(32), default="depends_on")
    relevance_score: Mapped[Decimal] = mapped_column(Numeric(7, 6))


class IndustryTaskEvidence(Base):
    __tablename__ = "rel_industry_task_evidence"

    industry_task_id: Mapped[int] = mapped_column(
        ForeignKey("biz_industry_task_candidate.industry_task_id"), primary_key=True
    )
    evidence_span_id: Mapped[int] = mapped_column(
        ForeignKey("biz_evidence_span.evidence_span_id"), primary_key=True
    )
    job_posting_id: Mapped[int | None] = mapped_column(ForeignKey("biz_job_posting.job_posting_id"))
    evidence_type_code: Mapped[str] = mapped_column(String(32))
    support_score: Mapped[Decimal] = mapped_column(Numeric(7, 6))


class TaskCommunity(Base):
    __tablename__ = "biz_task_community"

    task_community_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    discovery_run_id: Mapped[int] = mapped_column(
        ForeignKey("biz_role_discovery_run.discovery_run_id")
    )
    community_code: Mapped[str] = mapped_column(String(64))
    community_label: Mapped[str] = mapped_column(String(500))
    grouping_method_code: Mapped[str] = mapped_column(String(32))
    cohesion_score: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    task_count: Mapped[int] = mapped_column(Integer, default=0)
    community_snapshot_json: Mapped[dict] = mapped_column(JSON)

    __table_args__ = (
        UniqueConstraint("discovery_run_id", "community_code", name="uk_discovery_community"),
    )


class TaskCommunityMember(Base):
    __tablename__ = "rel_task_community_member"

    task_community_id: Mapped[int] = mapped_column(
        ForeignKey("biz_task_community.task_community_id"), primary_key=True
    )
    industry_task_id: Mapped[int] = mapped_column(
        ForeignKey("biz_industry_task_candidate.industry_task_id"), primary_key=True
    )
    member_role_code: Mapped[str] = mapped_column(String(32), default="core")
    membership_score: Mapped[Decimal] = mapped_column(Numeric(7, 6))


class EmergingRoleCandidate(Base):
    __tablename__ = "biz_emerging_role_candidate"

    emerging_role_candidate_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    discovery_run_id: Mapped[int] = mapped_column(
        ForeignKey("biz_role_discovery_run.discovery_run_id")
    )
    task_community_id: Mapped[int | None] = mapped_column(
        ForeignKey("biz_task_community.task_community_id")
    )
    candidate_code: Mapped[str] = mapped_column(String(64), unique=True)
    # 由推演模式 + 技术组合派生的稳定标识：同一组合在后续运行中复用同一行，
    # 避免每跑一次就产生一整批同名候选。
    candidate_key: Mapped[str] = mapped_column(String(64), unique=True)
    proposed_name: Mapped[str] = mapped_column(String(500))
    normalized_name: Mapped[str] = mapped_column(String(500))
    maturity_stage_code: Mapped[str] = mapped_column(String(32))
    workflow_status_code: Mapped[str] = mapped_column(String(32), default="pending")
    candidate_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    # 支撑该候选的 JD 数。从机械事实卡下沉为列，使「按证据量排序」可排可索引。
    support_job_count: Mapped[int] = mapped_column(Integer, default=0)
    nearest_job_role_id: Mapped[int | None] = mapped_column(ForeignKey("biz_job_role.job_role_id"))
    overlap_score: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    classification_code: Mapped[str] = mapped_column(String(32))
    # 最后一次为该候选计算评分的推演运行。候选一次创建、永久保留，而每轮只重算
    # 排名前 max_communities 的组合，名额之外的候选会带着旧版算法的评分留在库里。
    # 提成真列后，「这个候选是不是当前算法算出来的」可直接查询与过滤。
    last_seen_discovery_run_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("biz_role_discovery_run.discovery_run_id"),
    )
    mechanical_card_json: Mapped[dict] = mapped_column(JSON)
    expression_json: Mapped[dict | None] = mapped_column(JSON)
    expression_model_version: Mapped[str | None] = mapped_column(String(100))
    risk_flags_json: Mapped[list] = mapped_column(JSON)
    approved_job_role_id: Mapped[int | None] = mapped_column(ForeignKey("biz_job_role.job_role_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_emerging_candidate_status", "workflow_status_code", "maturity_stage_code"),
    )


class CandidateScoreComponent(Base):
    __tablename__ = "biz_candidate_score_component"

    candidate_score_component_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    emerging_role_candidate_id: Mapped[int] = mapped_column(
        ForeignKey("biz_emerging_role_candidate.emerging_role_candidate_id")
    )
    component_code: Mapped[str] = mapped_column(String(64))
    component_type_code: Mapped[str] = mapped_column(String(16))
    raw_score: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    weight: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    weighted_score: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    explanation_json: Mapped[dict | None] = mapped_column(JSON)

    __table_args__ = (
        UniqueConstraint(
            "emerging_role_candidate_id", "component_code", name="uk_candidate_score_component"
        ),
    )


class CandidateTechnology(Base):
    __tablename__ = "rel_candidate_technology"

    emerging_role_candidate_id: Mapped[int] = mapped_column(
        ForeignKey("biz_emerging_role_candidate.emerging_role_candidate_id"), primary_key=True
    )
    technology_node_id: Mapped[int] = mapped_column(
        ForeignKey("md_technology_node.technology_node_id"), primary_key=True
    )
    # core = 挖掘出的核心组合，决定候选身份、去重键与覆盖率测量；
    # profile = 由支撑 JD 扩展出的画像，只供 JD 生成与展示，不参与上述判定。
    membership_code: Mapped[str] = mapped_column(String(16), default="core")
    requirement_type_code: Mapped[str] = mapped_column(String(32))
    importance_score: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)


class StandardJobDescription(Base):
    __tablename__ = "biz_standard_job_description"

    standard_jd_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    standard_jd_code: Mapped[str] = mapped_column(String(64), unique=True)
    emerging_role_candidate_id: Mapped[int] = mapped_column(
        ForeignKey("biz_emerging_role_candidate.emerging_role_candidate_id")
    )
    job_role_version_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_role_version.job_role_version_id")
    )
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    title_text: Mapped[str] = mapped_column(String(500))
    content_json: Mapped[dict] = mapped_column(JSON)
    generation_method_code: Mapped[str] = mapped_column(String(32), default="mechanical")
    model_version: Mapped[str | None] = mapped_column(String(100))
    is_market_evidence: Mapped[bool] = mapped_column(Boolean, default=False)
    data_origin_code: Mapped[str] = mapped_column(String(32), default="algorithm_inference")
    approval_status_code: Mapped[str] = mapped_column(String(32), default="approved")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "emerging_role_candidate_id", "version_no", name="uk_candidate_standard_jd"
        ),
    )
