from datetime import date, datetime
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


class JobScenario(Base):
    """JD 应用场景条目（后端设计 §7.1 application_scenarios[]）。"""

    __tablename__ = "rel_job_scenario"

    job_scenario_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    job_parse_run_id: Mapped[int] = mapped_column(ForeignKey("biz_job_parse_run.job_parse_run_id"))
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("biz_job_posting.job_posting_id"))
    scenario_no: Mapped[int] = mapped_column(Integer)
    scenario_text: Mapped[str] = mapped_column(Text)
    normalized_scenario: Mapped[str] = mapped_column(String(500))
    start_offset: Mapped[int] = mapped_column(Integer, default=0)
    end_offset: Mapped[int] = mapped_column(Integer, default=0)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    data_origin_code: Mapped[str] = mapped_column(String(32), default="source_fact")

    __table_args__ = (
        # 场景是解析运行的派生物（同 JobResponsibility）。缺少 run 维度会让第二次
        # 解析必然主键冲突，岗位能力更新因此从未跑通。
        UniqueConstraint(
            "job_parse_run_id", "job_posting_id", "scenario_no", name="uk_job_scenario_run_no"
        ),
        Index("idx_job_scenario_posting", "job_posting_id"),
    )


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
    job_title_normalized: Mapped[str] = mapped_column(String(1000))
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
    data_origin_code: Mapped[str] = mapped_column(String(32), default="source_fact")
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


class JobParseRun(Base):
    __tablename__ = "biz_job_parse_run"

    job_parse_run_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    run_code: Mapped[str] = mapped_column(String(64), unique=True)
    parser_version: Mapped[str] = mapped_column(String(64))
    taxonomy_version_id: Mapped[int] = mapped_column(
        ForeignKey("md_technology_taxonomy_version.taxonomy_version_id")
    )
    target_date: Mapped[date] = mapped_column()
    input_snapshot_hash: Mapped[str] = mapped_column(String(64))
    config_json: Mapped[dict | None] = mapped_column(JSON)
    run_status_code: Mapped[str] = mapped_column(String(32), default="running")
    input_job_count: Mapped[int] = mapped_column(Integer, default=0)
    parsed_job_count: Mapped[int] = mapped_column(Integer, default=0)
    review_job_count: Mapped[int] = mapped_column(Integer, default=0)
    responsibility_count: Mapped[int] = mapped_column(Integer, default=0)
    assessment_count: Mapped[int] = mapped_column(Integer, default=0)
    feature_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (Index("idx_job_parse_run_status", "run_status_code", "target_date"),)


class JobParseResult(Base):
    __tablename__ = "rel_job_parse_result"

    job_parse_run_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_parse_run.job_parse_run_id"), primary_key=True
    )
    job_posting_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_posting.job_posting_id"), primary_key=True
    )
    source_document_version_id: Mapped[int] = mapped_column(
        ForeignKey("raw_source_document_version.source_document_version_id")
    )
    content_hash: Mapped[str] = mapped_column(String(64))
    parse_status_code: Mapped[str] = mapped_column(String(32))
    responsibility_count: Mapped[int] = mapped_column(Integer, default=0)
    required_segment_count: Mapped[int] = mapped_column(Integer, default=0)
    bonus_segment_count: Mapped[int] = mapped_column(Integer, default=0)
    unknown_segment_count: Mapped[int] = mapped_column(Integer, default=0)
    ambiguity_review_count: Mapped[int] = mapped_column(Integer, default=0)
    parse_quality_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    reason_json: Mapped[dict | None] = mapped_column(JSON)
    parsed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_job_parse_result_review", "job_parse_run_id", "review_required"),
        Index("idx_job_parse_result_quality", "job_parse_run_id", "parse_quality_score"),
    )


class JobResponsibility(Base):
    __tablename__ = "biz_job_responsibility"

    job_responsibility_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    job_parse_run_id: Mapped[int] = mapped_column(ForeignKey("biz_job_parse_run.job_parse_run_id"))
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("biz_job_posting.job_posting_id"))
    responsibility_no: Mapped[int] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text)
    normalized_task_text: Mapped[str | None] = mapped_column(Text)
    action_verb: Mapped[str | None] = mapped_column(String(100))
    task_object: Mapped[str | None] = mapped_column(String(500))
    expected_output: Mapped[str | None] = mapped_column(String(500))
    extraction_method_code: Mapped[str] = mapped_column(String(64))
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))

    __table_args__ = (
        UniqueConstraint(
            "job_parse_run_id",
            "job_posting_id",
            "responsibility_no",
            name="uk_job_responsibility_run_no",
        ),
        Index("idx_job_responsibility_job", "job_posting_id", "job_parse_run_id"),
    )


class JobFactEvidence(Base):
    __tablename__ = "rel_job_fact_evidence"

    job_fact_evidence_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    job_parse_run_id: Mapped[int] = mapped_column(ForeignKey("biz_job_parse_run.job_parse_run_id"))
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("biz_job_posting.job_posting_id"))
    target_type_code: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[int] = mapped_column(BigInteger)
    evidence_span_id: Mapped[int] = mapped_column(ForeignKey("biz_evidence_span.evidence_span_id"))
    support_type_code: Mapped[str] = mapped_column(String(32), default="support")
    support_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))

    __table_args__ = (
        UniqueConstraint(
            "job_parse_run_id",
            "target_type_code",
            "target_id",
            "evidence_span_id",
            "support_type_code",
            name="uk_job_fact_evidence_run",
        ),
    )


class TechnologyAmbiguityRule(Base):
    __tablename__ = "md_technology_ambiguity_rule"

    technology_ambiguity_rule_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    rule_code: Mapped[str] = mapped_column(String(64), unique=True)
    normalized_alias: Mapped[str] = mapped_column(String(500))
    technology_node_id: Mapped[int] = mapped_column(
        ForeignKey("md_technology_node.technology_node_id")
    )
    positive_markers_json: Mapped[list] = mapped_column(JSON)
    missing_context_decision_code: Mapped[str] = mapped_column(String(32), default="needs_review")
    review_weight: Mapped[Decimal] = mapped_column(Numeric(7, 4), default=Decimal("0.35"))
    rule_version: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "normalized_alias", "technology_node_id", name="uk_ambiguity_alias_technology"
        ),
        Index("idx_ambiguity_rule_active", "is_active", "normalized_alias"),
    )


class TechnologyMatchAssessment(Base):
    __tablename__ = "biz_technology_match_assessment"

    technology_match_assessment_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    job_parse_run_id: Mapped[int] = mapped_column(ForeignKey("biz_job_parse_run.job_parse_run_id"))
    job_requirement_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_requirement.job_requirement_id")
    )
    evidence_span_id: Mapped[int] = mapped_column(ForeignKey("biz_evidence_span.evidence_span_id"))
    context_evidence_span_id: Mapped[int | None] = mapped_column(
        ForeignKey("biz_evidence_span.evidence_span_id")
    )
    ambiguity_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("md_technology_ambiguity_rule.technology_ambiguity_rule_id")
    )
    context_type_code: Mapped[str] = mapped_column(String(32))
    assessment_status_code: Mapped[str] = mapped_column(String(32))
    adjusted_support_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    feature_weight: Mapped[Decimal] = mapped_column(Numeric(7, 4))
    reason_code: Mapped[str] = mapped_column(String(64))
    assessed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "job_parse_run_id",
            "job_requirement_id",
            "evidence_span_id",
            name="uk_match_assessment_run_evidence",
        ),
        Index(
            "idx_match_assessment_review",
            "job_parse_run_id",
            "assessment_status_code",
            "reason_code",
        ),
    )


class LlmTechnologyReassessmentRun(Base):
    """一次受限的 LLM 技术命中复核运行。"""

    __tablename__ = "biz_llm_technology_reassessment_run"

    reassessment_run_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    run_code: Mapped[str] = mapped_column(String(64), unique=True)
    job_parse_run_id: Mapped[int] = mapped_column(ForeignKey("biz_job_parse_run.job_parse_run_id"))
    model_version: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(64))
    input_snapshot_hash: Mapped[str] = mapped_column(String(64))
    config_json: Mapped[dict] = mapped_column(JSON)
    run_status_code: Mapped[str] = mapped_column(String(32), default="running")
    input_assessment_count: Mapped[int] = mapped_column(Integer, default=0)
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    uncertain_count: Mapped[int] = mapped_column(Integer, default=0)
    validation_failure_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        Index(
            "idx_llm_technology_reassessment_run",
            "job_parse_run_id",
            "run_status_code",
        ),
    )


class LlmTechnologyReassessment(Base):
    """逐条保存模型原始决定、证据校验与是否回写，便于审计和回滚。"""

    __tablename__ = "biz_llm_technology_reassessment"

    reassessment_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    reassessment_run_id: Mapped[int] = mapped_column(
        ForeignKey("biz_llm_technology_reassessment_run.reassessment_run_id")
    )
    technology_match_assessment_id: Mapped[int] = mapped_column(
        ForeignKey("biz_technology_match_assessment.technology_match_assessment_id")
    )
    original_status_code: Mapped[str] = mapped_column(String(32))
    decision_code: Mapped[str] = mapped_column(String(32))
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    evidence_quote: Mapped[str | None] = mapped_column(Text)
    reason_code: Mapped[str] = mapped_column(String(64))
    reason_text: Mapped[str | None] = mapped_column(Text)
    raw_response_json: Mapped[dict | None] = mapped_column(JSON)
    validation_status_code: Mapped[str] = mapped_column(String(32))
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    input_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "reassessment_run_id",
            "technology_match_assessment_id",
            name="uk_llm_technology_reassessment_item",
        ),
        Index(
            "idx_llm_technology_reassessment_decision",
            "reassessment_run_id",
            "decision_code",
            "validation_status_code",
        ),
    )


class JobClusterFeatureSnapshot(Base):
    __tablename__ = "biz_job_cluster_feature_snapshot"

    job_parse_run_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_parse_run.job_parse_run_id"), primary_key=True
    )
    job_posting_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_posting.job_posting_id"), primary_key=True
    )
    feature_version: Mapped[str] = mapped_column(String(64))
    title_tokens_json: Mapped[list] = mapped_column(JSON)
    responsibility_tokens_json: Mapped[list] = mapped_column(JSON)
    technology_weights_json: Mapped[dict] = mapped_column(JSON)
    domain_weights_json: Mapped[dict] = mapped_column(JSON)
    level_code: Mapped[str | None] = mapped_column(String(32))
    sample_weight: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    time_quality_code: Mapped[str] = mapped_column(String(32))
    feature_hash: Mapped[str] = mapped_column(String(64))
    eligible_for_clustering: Mapped[bool] = mapped_column(Boolean, default=True)
    exclusion_reason_json: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index(
            "idx_cluster_feature_eligible",
            "job_parse_run_id",
            "eligible_for_clustering",
            "time_quality_code",
        ),
    )
