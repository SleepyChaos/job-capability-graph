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


class JobClusteringRun(Base):
    __tablename__ = "biz_job_clustering_run"

    clustering_run_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    run_code: Mapped[str] = mapped_column(String(64), unique=True)
    job_parse_run_id: Mapped[int] = mapped_column(ForeignKey("biz_job_parse_run.job_parse_run_id"))
    run_type_code: Mapped[str] = mapped_column(String(32), default="full")
    target_date: Mapped[date] = mapped_column(Date)
    window_start_date: Mapped[date | None] = mapped_column(Date)
    feature_version: Mapped[str] = mapped_column(String(64))
    embedding_model_version: Mapped[str | None] = mapped_column(String(100))
    algorithm_name: Mapped[str] = mapped_column(String(100))
    algorithm_version: Mapped[str] = mapped_column(String(64))
    parameter_json: Mapped[dict] = mapped_column(JSON)
    input_snapshot_hash: Mapped[str] = mapped_column(String(64))
    input_job_count: Mapped[int] = mapped_column(Integer, default=0)
    assigned_job_count: Mapped[int] = mapped_column(Integer, default=0)
    grey_job_count: Mapped[int] = mapped_column(Integer, default=0)
    output_cluster_count: Mapped[int] = mapped_column(Integer, default=0)
    candidate_role_count: Mapped[int] = mapped_column(Integer, default=0)
    quality_metric_json: Mapped[dict | None] = mapped_column(JSON)
    run_status_code: Mapped[str] = mapped_column(String(32), default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "job_parse_run_id",
            "algorithm_version",
            "input_snapshot_hash",
            name="uk_clustering_run_input",
        ),
        Index("idx_clustering_run_status", "run_status_code", "target_date"),
    )


class JobClusterVersion(Base):
    __tablename__ = "biz_job_cluster_version"

    job_cluster_version_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    clustering_run_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_clustering_run.clustering_run_id")
    )
    stable_cluster_code: Mapped[str] = mapped_column(String(64))
    cluster_label: Mapped[str] = mapped_column(String(300))
    cluster_description: Mapped[str | None] = mapped_column(Text)
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    independent_organization_count: Mapped[int] = mapped_column(Integer, default=0)
    centroid_json: Mapped[dict] = mapped_column(JSON)
    representative_job_ids_json: Mapped[list] = mapped_column(JSON)
    silhouette_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    coherence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    cluster_status_code: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("clustering_run_id", "stable_cluster_code", name="uk_cluster_run_stable"),
        Index("idx_cluster_run_size", "clustering_run_id", "member_count"),
    )


class JobClusterMember(Base):
    __tablename__ = "rel_job_cluster_member"

    job_cluster_version_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_cluster_version.job_cluster_version_id"), primary_key=True
    )
    job_posting_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_posting.job_posting_id"), primary_key=True
    )
    similarity_score: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    assignment_method_code: Mapped[str] = mapped_column(String(32), default="baseline")
    assignment_status_code: Mapped[str] = mapped_column(String(32))
    assignment_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    similarity_breakdown_json: Mapped[dict] = mapped_column(JSON)
    top_candidates_json: Mapped[list] = mapped_column(JSON)
    is_representative: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (Index("idx_cluster_member_job", "job_posting_id"),)


class JobClusterLineage(Base):
    __tablename__ = "rel_job_cluster_lineage"

    job_cluster_lineage_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    from_cluster_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("biz_job_cluster_version.job_cluster_version_id")
    )
    to_cluster_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("biz_job_cluster_version.job_cluster_version_id")
    )
    lineage_type_code: Mapped[str] = mapped_column(String(32))
    member_overlap_score: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    explanation_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "from_cluster_version_id",
            "to_cluster_version_id",
            "lineage_type_code",
            name="uk_cluster_lineage",
        ),
    )


class JobClusterDomain(Base):
    __tablename__ = "rel_job_cluster_domain"

    job_cluster_version_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_cluster_version.job_cluster_version_id"), primary_key=True
    )
    technology_domain_id: Mapped[int] = mapped_column(
        ForeignKey("md_technology_domain.technology_domain_id"), primary_key=True
    )
    domain_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    calculation_version: Mapped[str] = mapped_column(String(64))
    review_status_code: Mapped[str] = mapped_column(String(32), default="unreviewed")


class JobRole(Base):
    __tablename__ = "biz_job_role"

    job_role_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    role_code: Mapped[str] = mapped_column(String(64), unique=True)
    canonical_name: Mapped[str] = mapped_column(String(300), unique=True)
    normalized_name: Mapped[str] = mapped_column(String(300), unique=True)
    origin_type_code: Mapped[str] = mapped_column(String(32), default="cluster_derived")
    lifecycle_status_code: Mapped[str] = mapped_column(String(32), default="candidate")
    first_detected_at: Mapped[datetime | None] = mapped_column(DateTime)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class JobRoleAlias(Base):
    __tablename__ = "md_job_role_alias"

    job_role_alias_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    job_role_id: Mapped[int] = mapped_column(ForeignKey("biz_job_role.job_role_id"))
    alias_text: Mapped[str] = mapped_column(String(500))
    normalized_alias: Mapped[str] = mapped_column(String(500))
    alias_type_code: Mapped[str] = mapped_column(String(32), default="source")
    is_searchable: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("job_role_id", "normalized_alias", name="uk_role_alias"),
        Index("idx_role_alias_lookup", "normalized_alias", "is_searchable"),
    )


class JobRoleVersion(Base):
    __tablename__ = "biz_job_role_version"

    job_role_version_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    job_role_id: Mapped[int] = mapped_column(ForeignKey("biz_job_role.job_role_id"))
    version_no: Mapped[int] = mapped_column(Integer)
    previous_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("biz_job_role_version.job_role_version_id")
    )
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    role_name: Mapped[str] = mapped_column(String(300))
    one_line_definition: Mapped[str] = mapped_column(Text)
    core_responsibility_text: Mapped[str] = mapped_column(Text)
    job_level_distribution_json: Mapped[dict | None] = mapped_column(JSON)
    update_summary: Mapped[str | None] = mapped_column(Text)
    generation_method_code: Mapped[str] = mapped_column(String(32), default="statistical")
    evidence_strength_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    approval_status_code: Mapped[str] = mapped_column(String(32), default="pending")
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("job_role_id", "version_no", name="uk_role_version_no"),
        Index("idx_role_version_current", "job_role_id", "approval_status_code", "valid_to"),
    )


class JobRoleVersionRequirement(Base):
    __tablename__ = "rel_job_role_version_requirement"

    role_version_requirement_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    job_role_version_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_role_version.job_role_version_id")
    )
    technology_node_id: Mapped[int] = mapped_column(
        ForeignKey("md_technology_node.technology_node_id")
    )
    requirement_type_code: Mapped[str] = mapped_column(String(32))
    required_level_code: Mapped[str | None] = mapped_column(String(32))
    long_term_importance_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    recent_activity_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    coverage_rate: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    required_ratio: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    trend_score: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    trend_status_code: Mapped[str] = mapped_column(String(32))
    supporting_job_count: Mapped[int] = mapped_column(Integer, default=0)
    independent_organization_count: Mapped[int] = mapped_column(Integer, default=0)
    independent_source_count: Mapped[int] = mapped_column(Integer, default=0)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    is_human_edited: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint(
            "job_role_version_id",
            "technology_node_id",
            "requirement_type_code",
            name="uk_role_version_technology",
        ),
        Index(
            "idx_role_requirement_graph",
            "job_role_version_id",
            "requirement_type_code",
            "long_term_importance_score",
        ),
    )


class JobClusterRole(Base):
    __tablename__ = "rel_job_cluster_role"

    job_cluster_version_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_cluster_version.job_cluster_version_id"), primary_key=True
    )
    job_role_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_role.job_role_id"), primary_key=True
    )
    relation_type_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)


class JobRoleEvidence(Base):
    __tablename__ = "rel_job_role_evidence"

    job_role_evidence_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    job_role_version_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_role_version.job_role_version_id")
    )
    role_version_requirement_id: Mapped[int | None] = mapped_column(
        ForeignKey("rel_job_role_version_requirement.role_version_requirement_id")
    )
    evidence_span_id: Mapped[int] = mapped_column(ForeignKey("biz_evidence_span.evidence_span_id"))
    evidence_role_code: Mapped[str] = mapped_column(String(32))
    support_type_code: Mapped[str] = mapped_column(String(32), default="support")
    support_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    source_organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("md_organization.organization_id")
    )

    __table_args__ = (
        UniqueConstraint(
            "job_role_version_id",
            "role_version_requirement_id",
            "evidence_span_id",
            "evidence_role_code",
            name="uk_role_evidence",
        ),
    )


class JobEvolutionEvent(Base):
    __tablename__ = "biz_job_evolution_event"

    job_evolution_event_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    event_code: Mapped[str] = mapped_column(String(64), unique=True)
    job_role_id: Mapped[int] = mapped_column(ForeignKey("biz_job_role.job_role_id"))
    from_role_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("biz_job_role_version.job_role_version_id")
    )
    to_role_version_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_role_version.job_role_version_id")
    )
    event_type_code: Mapped[str] = mapped_column(String(32))
    change_summary: Mapped[str] = mapped_column(Text)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    approval_status_code: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class JobEvolutionChange(Base):
    __tablename__ = "biz_job_evolution_change"

    job_evolution_change_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    job_evolution_event_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_evolution_event.job_evolution_event_id")
    )
    technology_node_id: Mapped[int | None] = mapped_column(
        ForeignKey("md_technology_node.technology_node_id")
    )
    capability_id: Mapped[int | None] = mapped_column(BigInteger)
    change_type_code: Mapped[str] = mapped_column(String(32))
    change_subtype_code: Mapped[str | None] = mapped_column(String(32))
    old_value_json: Mapped[dict | None] = mapped_column(JSON)
    new_value_json: Mapped[dict | None] = mapped_column(JSON)
    change_magnitude: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    change_reason: Mapped[str | None] = mapped_column(Text)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index("idx_evolution_change_event", "job_evolution_event_id", "change_type_code"),
    )
