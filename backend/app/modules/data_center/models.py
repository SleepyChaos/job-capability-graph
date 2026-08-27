from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
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


class AppUser(Base):
    __tablename__ = "app_user"

    user_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    user_code: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    role_code: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SourceCollectionPolicy(Base):
    __tablename__ = "md_source_collection_policy"

    collection_policy_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    data_source_id: Mapped[int] = mapped_column(ForeignKey("md_data_source.data_source_id"))
    policy_version: Mapped[str] = mapped_column(String(64))
    list_page_rule_json: Mapped[dict | None] = mapped_column(JSON)
    detail_page_rule_json: Mapped[dict | None] = mapped_column(JSON)
    pagination_rule_json: Mapped[dict | None] = mapped_column(JSON)
    max_depth: Mapped[int] = mapped_column(Integer, default=1)
    schedule_cron: Mapped[str | None] = mapped_column(String(100))
    timezone_name: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=30)
    domain_concurrency: Mapped[int] = mapped_column(Integer, default=1)
    robots_status_code: Mapped[str] = mapped_column(String(32), default="unchecked")
    terms_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    allowed_scope_json: Mapped[dict | None] = mapped_column(JSON)
    parser_code: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint("max_depth >= 0 AND max_depth <= 1", name="collection_policy_depth"),
        UniqueConstraint("data_source_id", "policy_version", name="uk_source_policy_version"),
    )


class CollectionRun(Base):
    __tablename__ = "biz_collection_run"

    collection_run_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    run_code: Mapped[str] = mapped_column(String(64), unique=True)
    data_source_id: Mapped[int] = mapped_column(ForeignKey("md_data_source.data_source_id"))
    collection_policy_id: Mapped[int] = mapped_column(
        ForeignKey("md_source_collection_policy.collection_policy_id")
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    run_status_code: Mapped[str] = mapped_column(String(32), default="pending")
    discovered_count: Mapped[int] = mapped_column(Integer, default=0)
    changed_count: Mapped[int] = mapped_column(Integer, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    cursor_json: Mapped[dict | None] = mapped_column(JSON)
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_collection_run_status", "run_status_code", "scheduled_at"),)


class CollectionRequest(Base):
    __tablename__ = "biz_collection_request"

    collection_request_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    collection_run_id: Mapped[int] = mapped_column(
        ForeignKey("biz_collection_run.collection_run_id")
    )
    parent_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("biz_collection_request.collection_request_id")
    )
    request_url: Mapped[str] = mapped_column(String(1500))
    normalized_url_hash: Mapped[str] = mapped_column(String(64))
    request_depth: Mapped[int] = mapped_column(Integer)
    request_type_code: Mapped[str] = mapped_column(String(32))
    response_status_code: Mapped[int | None] = mapped_column(Integer)
    response_content_hash: Mapped[str | None] = mapped_column(String(64))
    response_file_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_file_asset.file_asset_id")
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    request_status_code: Mapped[str] = mapped_column(String(32), default="pending")
    parse_status_code: Mapped[str] = mapped_column(String(32), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        CheckConstraint(
            "request_depth >= 0 AND request_depth <= 1", name="collection_request_depth"
        ),
        UniqueConstraint(
            "collection_run_id", "normalized_url_hash", name="uk_collection_request_url"
        ),
        Index("idx_collection_request_status", "collection_run_id", "request_status_code"),
    )


class ExtractionRun(Base):
    __tablename__ = "biz_extraction_run"

    extraction_run_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    run_code: Mapped[str] = mapped_column(String(64), unique=True)
    source_document_version_id: Mapped[int] = mapped_column(
        ForeignKey("raw_source_document_version.source_document_version_id")
    )
    extractor_code: Mapped[str] = mapped_column(String(64))
    extractor_version: Mapped[str] = mapped_column(String(64))
    input_hash: Mapped[str] = mapped_column(String(64))
    run_status_code: Mapped[str] = mapped_column(String(32), default="success")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ExtractedFact(Base):
    __tablename__ = "biz_extracted_fact"

    extracted_fact_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    extraction_run_id: Mapped[int] = mapped_column(
        ForeignKey("biz_extraction_run.extraction_run_id")
    )
    fact_code: Mapped[str] = mapped_column(String(64), unique=True)
    fact_type_code: Mapped[str] = mapped_column(String(32))
    normalized_value_json: Mapped[dict] = mapped_column(JSON)
    extraction_confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    publish_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    fact_status_code: Mapped[str] = mapped_column(String(32), default="candidate")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_extracted_fact_status", "fact_type_code", "fact_status_code"),)


class FactEvidence(Base):
    __tablename__ = "rel_fact_evidence"

    extracted_fact_id: Mapped[int] = mapped_column(
        ForeignKey("biz_extracted_fact.extracted_fact_id"), primary_key=True
    )
    evidence_span_id: Mapped[int] = mapped_column(
        ForeignKey("biz_evidence_span.evidence_span_id"), primary_key=True
    )
    support_type_code: Mapped[str] = mapped_column(String(32), default="direct")
    support_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))


class FactValidation(Base):
    __tablename__ = "biz_fact_validation"

    fact_validation_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    extracted_fact_id: Mapped[int] = mapped_column(
        ForeignKey("biz_extracted_fact.extracted_fact_id")
    )
    validator_code: Mapped[str] = mapped_column(String(64))
    validation_status_code: Mapped[str] = mapped_column(String(32))
    hard_error_count: Mapped[int] = mapped_column(Integer, default=0)
    score_breakdown_json: Mapped[dict] = mapped_column(JSON)
    reason_json: Mapped[dict | None] = mapped_column(JSON)
    validated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ReviewTask(Base):
    __tablename__ = "biz_review_task"

    review_task_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    task_code: Mapped[str] = mapped_column(String(64), unique=True)
    queue_code: Mapped[str] = mapped_column(String(32))
    target_type_code: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[int] = mapped_column(BigInteger)
    priority_score: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    task_status_code: Mapped[str] = mapped_column(String(32), default="queued")
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
    target_snapshot_json: Mapped[dict] = mapped_column(JSON)
    reason_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("queue_code", "target_type_code", "target_id", name="uk_review_target"),
        Index("idx_review_queue_status", "queue_code", "task_status_code", "priority_score"),
    )


class ReviewAction(Base):
    __tablename__ = "biz_review_action"

    review_action_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    review_task_id: Mapped[int] = mapped_column(ForeignKey("biz_review_task.review_task_id"))
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("app_user.user_id"))
    action_code: Mapped[str] = mapped_column(String(32))
    from_status_code: Mapped[str] = mapped_column(String(32))
    to_status_code: Mapped[str] = mapped_column(String(32))
    comment_text: Mapped[str | None] = mapped_column(Text)
    before_snapshot_json: Mapped[dict] = mapped_column(JSON)
    after_snapshot_json: Mapped[dict] = mapped_column(JSON)
    acted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MilestoneEvent(Base):
    __tablename__ = "biz_milestone_event"

    milestone_event_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    milestone_code: Mapped[str] = mapped_column(String(64), unique=True)
    extracted_fact_id: Mapped[int] = mapped_column(
        ForeignKey("biz_extracted_fact.extracted_fact_id"), unique=True
    )
    milestone_name: Mapped[str] = mapped_column(String(500))
    milestone_type_code: Mapped[str] = mapped_column(String(32))
    event_date: Mapped[date | None] = mapped_column(Date)
    event_year: Mapped[int] = mapped_column(Integer)
    description_text: Mapped[str] = mapped_column(Text)
    maturity_delta_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    verification_status_code: Mapped[str] = mapped_column(String(32), default="candidate")
    data_origin_code: Mapped[str] = mapped_column(String(32), default="source_fact")
    verified_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("event_year >= 1900 AND event_year <= 2200", name="milestone_event_year"),
        Index("idx_milestone_status_year", "verification_status_code", "event_year"),
    )


class MilestoneTechnology(Base):
    __tablename__ = "rel_milestone_technology"

    milestone_event_id: Mapped[int] = mapped_column(
        ForeignKey("biz_milestone_event.milestone_event_id"), primary_key=True
    )
    technology_node_id: Mapped[int] = mapped_column(
        ForeignKey("md_technology_node.technology_node_id"), primary_key=True
    )
    relation_type_code: Mapped[str] = mapped_column(String(32), default="advances")
    relevance_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    is_human_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class MilestoneEvidence(Base):
    __tablename__ = "rel_milestone_evidence"

    milestone_event_id: Mapped[int] = mapped_column(
        ForeignKey("biz_milestone_event.milestone_event_id"), primary_key=True
    )
    evidence_span_id: Mapped[int] = mapped_column(
        ForeignKey("biz_evidence_span.evidence_span_id"), primary_key=True
    )
    evidence_role_code: Mapped[str] = mapped_column(String(32), default="primary")
