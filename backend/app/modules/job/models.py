from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
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


class Organization(Base):
    __tablename__ = "md_organization"

    organization_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    source_spreadsheet_row_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_spreadsheet_row.spreadsheet_row_id")
    )
    organization_code: Mapped[str] = mapped_column(String(64), unique=True)
    canonical_name: Mapped[str] = mapped_column(String(500))
    normalized_name: Mapped[str] = mapped_column(String(500))
    organization_type_code: Mapped[str] = mapped_column(String(32), default="enterprise")
    country_code: Mapped[str | None] = mapped_column(String(16))
    province_name: Mapped[str | None] = mapped_column(String(100))
    city_name: Mapped[str | None] = mapped_column(String(100))
    website_url: Mapped[str | None] = mapped_column(String(1500))
    industry_text: Mapped[str | None] = mapped_column(String(500))
    source_metadata_json: Mapped[dict | None] = mapped_column(JSON)
    organization_status_code: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_org_name", "normalized_name"),
        Index("idx_org_type_region", "organization_type_code", "province_name", "city_name"),
    )


class OrganizationAlias(Base):
    __tablename__ = "md_organization_alias"

    organization_alias_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("md_organization.organization_id"))
    source_spreadsheet_row_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_spreadsheet_row.spreadsheet_row_id")
    )
    alias_text: Mapped[str] = mapped_column(String(500))
    normalized_alias: Mapped[str] = mapped_column(String(500))
    alias_type_code: Mapped[str] = mapped_column(String(32), default="source")

    __table_args__ = (
        UniqueConstraint("organization_id", "normalized_alias", name="uk_org_alias"),
        Index("idx_org_alias_lookup", "normalized_alias"),
    )


class DataSource(Base):
    __tablename__ = "md_data_source"

    data_source_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    source_file_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_file_asset.file_asset_id")
    )
    source_code: Mapped[str] = mapped_column(String(64), unique=True)
    source_name: Mapped[str] = mapped_column(String(300))
    source_type_code: Mapped[str] = mapped_column(String(32))
    owner_organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("md_organization.organization_id")
    )
    entry_url: Mapped[str | None] = mapped_column(String(1500))
    content_type_code: Mapped[str] = mapped_column(String(32), default="job")
    authority_level_code: Mapped[str | None] = mapped_column(String(32))
    independent_source_group: Mapped[str | None] = mapped_column(String(128))
    default_reliability_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    license_note: Mapped[str | None] = mapped_column(Text)
    source_status_code: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class SourceDocument(Base):
    __tablename__ = "raw_source_document"

    source_document_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    source_spreadsheet_row_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_spreadsheet_row.spreadsheet_row_id")
    )
    document_code: Mapped[str] = mapped_column(String(64), unique=True)
    data_source_id: Mapped[int] = mapped_column(ForeignKey("md_data_source.data_source_id"))
    document_type_code: Mapped[str] = mapped_column(String(32), default="job")
    source_record_key: Mapped[str | None] = mapped_column(String(500))
    canonical_url: Mapped[str | None] = mapped_column(String(1500))
    document_identity_key: Mapped[str] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(String(1000))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime)
    missing_successive_runs: Mapped[int] = mapped_column(Integer, default=0)
    document_status_code: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "data_source_id", "document_identity_key", name="uk_source_document_identity"
        ),
        Index("idx_document_type_seen", "document_type_code", "last_seen_at"),
    )


class SourceDocumentVersion(Base):
    __tablename__ = "raw_source_document_version"

    source_document_version_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    source_document_id: Mapped[int] = mapped_column(
        ForeignKey("raw_source_document.source_document_id")
    )
    collection_run_id: Mapped[int | None] = mapped_column(BigInteger)
    version_no: Mapped[int] = mapped_column(Integer)
    previous_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_source_document_version.source_document_version_id")
    )
    file_asset_id: Mapped[int | None] = mapped_column(ForeignKey("raw_file_asset.file_asset_id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    collected_at: Mapped[datetime] = mapped_column(DateTime)
    source_collected_at: Mapped[datetime | None] = mapped_column(DateTime)
    valid_from: Mapped[datetime] = mapped_column(DateTime)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime)
    content_text: Mapped[str] = mapped_column(Text)
    content_json: Mapped[dict | None] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    parser_version: Mapped[str | None] = mapped_column(String(64))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("source_document_id", "version_no", name="uk_document_version_no"),
        UniqueConstraint("source_document_id", "content_hash", name="uk_document_content_hash"),
        Index("idx_document_current", "source_document_id", "is_current", "valid_from"),
    )


class DocumentQuality(Base):
    __tablename__ = "biz_document_quality"

    document_quality_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    source_document_version_id: Mapped[int] = mapped_column(
        ForeignKey("raw_source_document_version.source_document_version_id")
    )
    checker_version: Mapped[str] = mapped_column(String(64))
    timeliness_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    completeness_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    noise_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    duplication_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    requirement_inflation_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    ai_generated_risk_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    prompt_injection_risk_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    overall_quality_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    quality_status_code: Mapped[str] = mapped_column(String(32))
    reason_json: Mapped[dict | None] = mapped_column(JSON)
    checked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "source_document_version_id", "checker_version", name="uk_document_quality_version"
        ),
    )


class DuplicateDocumentGroup(Base):
    __tablename__ = "biz_duplicate_document_group"

    duplicate_group_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    group_code: Mapped[str] = mapped_column(String(64), unique=True)
    representative_document_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_source_document_version.source_document_version_id")
    )
    detection_method_code: Mapped[str] = mapped_column(String(32))
    algorithm_version: Mapped[str] = mapped_column(String(64))
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DuplicateDocumentMember(Base):
    __tablename__ = "rel_duplicate_document_member"

    duplicate_group_id: Mapped[int] = mapped_column(
        ForeignKey("biz_duplicate_document_group.duplicate_group_id"), primary_key=True
    )
    source_document_version_id: Mapped[int] = mapped_column(
        ForeignKey("raw_source_document_version.source_document_version_id"), primary_key=True
    )
    similarity_score: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    copied_ratio: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    is_representative: Mapped[bool] = mapped_column(Boolean, default=False)


class EvidenceSpan(Base):
    __tablename__ = "biz_evidence_span"

    evidence_span_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    source_document_version_id: Mapped[int] = mapped_column(
        ForeignKey("raw_source_document_version.source_document_version_id")
    )
    span_type_code: Mapped[str] = mapped_column(String(32))
    page_no: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    evidence_text: Mapped[str] = mapped_column(Text)
    evidence_hash: Mapped[str] = mapped_column(String(64))
    source_reliability_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("source_document_version_id", "evidence_hash", name="uk_evidence_hash"),
    )


class JobPosting(Base):
    __tablename__ = "biz_job_posting"

    job_posting_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    source_spreadsheet_row_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_spreadsheet_row.spreadsheet_row_id")
    )
    job_code: Mapped[str] = mapped_column(String(64), unique=True)
    source_document_version_id: Mapped[int] = mapped_column(
        ForeignKey("raw_source_document_version.source_document_version_id"), unique=True
    )
    data_source_id: Mapped[int] = mapped_column(ForeignKey("md_data_source.data_source_id"))
    source_job_id: Mapped[str | None] = mapped_column(String(300))
    source_group_key: Mapped[str | None] = mapped_column(String(300))
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("md_organization.organization_id")
    )
    company_name_raw: Mapped[str | None] = mapped_column(String(500))
    job_title_raw: Mapped[str] = mapped_column(String(1000))
    job_title_normalized: Mapped[str] = mapped_column(String(500))
    employment_type_code: Mapped[str | None] = mapped_column(String(32))
    job_level_code: Mapped[str | None] = mapped_column(String(32))
    region_text: Mapped[str | None] = mapped_column(String(300))
    salary_text: Mapped[str | None] = mapped_column(String(300))
    salary_min_monthly_cny: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    salary_max_monthly_cny: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    salary_months_per_year: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    education_code: Mapped[str | None] = mapped_column(String(32))
    education_text: Mapped[str | None] = mapped_column(String(200))
    experience_min_years: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    experience_max_years: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    experience_text: Mapped[str | None] = mapped_column(String(200))
    jd_clean_text: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    collected_at: Mapped[datetime] = mapped_column(DateTime)
    source_collected_at: Mapped[datetime | None] = mapped_column(DateTime)
    time_quality_code: Mapped[str] = mapped_column(String(32))
    expired_at: Mapped[datetime | None] = mapped_column(DateTime)
    posting_status_code: Mapped[str] = mapped_column(String(32), default="active")
    parse_confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    publish_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    evidence_weight: Mapped[Decimal] = mapped_column(Numeric(9, 6), default=Decimal("1"))
    source_metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_job_title_time", "job_title_normalized", "published_at"),
        Index("idx_job_org_status", "organization_id", "posting_status_code", "collected_at"),
        Index("idx_job_time_quality", "time_quality_code", "source_collected_at"),
    )


class JobPostingDataSource(Base):
    __tablename__ = "rel_job_posting_data_source"

    job_posting_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_posting.job_posting_id"), primary_key=True
    )
    data_source_id: Mapped[int] = mapped_column(
        ForeignKey("md_data_source.data_source_id"), primary_key=True
    )
    source_role_code: Mapped[str] = mapped_column(String(32))
    source_order: Mapped[int] = mapped_column(Integer)


class JobRequirement(Base):
    __tablename__ = "biz_job_requirement"

    job_requirement_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("biz_job_posting.job_posting_id"))
    requirement_no: Mapped[int] = mapped_column(Integer)
    requirement_type_code: Mapped[str] = mapped_column(String(32))
    raw_term: Mapped[str | None] = mapped_column(String(500))
    raw_text: Mapped[str] = mapped_column(Text)
    technology_node_id: Mapped[int | None] = mapped_column(
        ForeignKey("md_technology_node.technology_node_id")
    )
    capability_id: Mapped[int | None] = mapped_column(BigInteger)
    required_level_code: Mapped[str | None] = mapped_column(String(32))
    required_level_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    mention_count: Mapped[int] = mapped_column(Integer, default=1)
    mapping_method_code: Mapped[str | None] = mapped_column(String(32))
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))

    __table_args__ = (
        UniqueConstraint("job_posting_id", "requirement_no", name="uk_job_requirement_no"),
        UniqueConstraint(
            "job_posting_id",
            "technology_node_id",
            "requirement_type_code",
            name="uk_job_requirement_technology_type",
        ),
        Index(
            "idx_job_requirement_technology",
            "technology_node_id",
            "requirement_type_code",
            "job_posting_id",
        ),
    )


class JobRequirementEvidence(Base):
    __tablename__ = "rel_job_requirement_evidence"

    job_requirement_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_requirement.job_requirement_id"), primary_key=True
    )
    evidence_span_id: Mapped[int] = mapped_column(
        ForeignKey("biz_evidence_span.evidence_span_id"), primary_key=True
    )
    matched_alias_id: Mapped[int] = mapped_column(
        ForeignKey("md_technology_alias.technology_alias_id")
    )
    support_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
