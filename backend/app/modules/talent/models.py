from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
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


class ResumeDocument(Base):
    __tablename__ = "raw_resume_document"

    resume_document_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    document_code: Mapped[str] = mapped_column(String(64), unique=True)
    source_name: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(150))
    input_type_code: Mapped[str] = mapped_column(String(32))
    content_hash: Mapped[str] = mapped_column(String(64))
    content_text: Mapped[str] = mapped_column(Text)
    safety_status_code: Mapped[str] = mapped_column(String(32), default="accepted")
    parser_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_resume_hash", "content_hash"),)


class CandidateProfile(Base):
    __tablename__ = "biz_candidate_profile"

    candidate_profile_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    profile_code: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    profile_status_code: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class CandidateProfileVersion(Base):
    __tablename__ = "biz_candidate_profile_version"

    candidate_profile_version_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    candidate_profile_id: Mapped[int] = mapped_column(
        ForeignKey("biz_candidate_profile.candidate_profile_id")
    )
    resume_document_id: Mapped[int] = mapped_column(
        ForeignKey("raw_resume_document.resume_document_id")
    )
    version_code: Mapped[str] = mapped_column(String(64), unique=True)
    version_no: Mapped[int] = mapped_column(Integer)
    previous_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("biz_candidate_profile_version.candidate_profile_version_id")
    )
    workflow_status_code: Mapped[str] = mapped_column(String(32), default="draft")
    target_role_text: Mapped[str | None] = mapped_column(String(500))
    education_text: Mapped[str | None] = mapped_column(String(500))
    experience_summary: Mapped[str | None] = mapped_column(Text)
    preference_json: Mapped[dict] = mapped_column(JSON, default=dict)
    fact_json: Mapped[dict] = mapped_column(JSON, default=dict)
    insight_json: Mapped[dict] = mapped_column(JSON, default=dict)
    completeness_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    conversation_round_count: Mapped[int] = mapped_column(Integer, default=0)
    parser_version: Mapped[str] = mapped_column(String(64))
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("candidate_profile_id", "version_no", name="uk_profile_version_no"),
        Index("idx_profile_version_status", "candidate_profile_id", "workflow_status_code"),
    )


class CandidateSkillEvidence(Base):
    __tablename__ = "rel_candidate_skill_evidence"

    candidate_skill_evidence_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    candidate_profile_version_id: Mapped[int] = mapped_column(
        ForeignKey("biz_candidate_profile_version.candidate_profile_version_id")
    )
    technology_node_id: Mapped[int] = mapped_column(
        ForeignKey("md_technology_node.technology_node_id")
    )
    raw_mention: Mapped[str] = mapped_column(String(500))
    evidence_text: Mapped[str] = mapped_column(Text)
    source_type_code: Mapped[str] = mapped_column(String(32))
    evidence_level_code: Mapped[str] = mapped_column(String(32), default="mentioned")
    proficiency_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    user_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "candidate_profile_version_id",
            "technology_node_id",
            "source_type_code",
            name="uk_profile_skill_source",
        ),
        Index("idx_profile_skill_technology", "technology_node_id"),
    )


class CandidateDialogueTurn(Base):
    __tablename__ = "biz_candidate_dialogue_turn"

    dialogue_turn_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    candidate_profile_version_id: Mapped[int] = mapped_column(
        ForeignKey("biz_candidate_profile_version.candidate_profile_version_id")
    )
    turn_no: Mapped[int] = mapped_column(Integer)
    question_code: Mapped[str] = mapped_column(String(64))
    question_text: Mapped[str] = mapped_column(Text)
    answer_text: Mapped[str | None] = mapped_column(Text)
    answer_source_code: Mapped[str] = mapped_column(String(32), default="user_supplement")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "candidate_profile_version_id", "turn_no", name="uk_profile_dialogue_turn"
        ),
    )


class CandidateMatchRun(Base):
    __tablename__ = "biz_candidate_match_run"

    candidate_match_run_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    run_code: Mapped[str] = mapped_column(String(64), unique=True)
    candidate_profile_version_id: Mapped[int] = mapped_column(
        ForeignKey("biz_candidate_profile_version.candidate_profile_version_id")
    )
    clustering_run_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_clustering_run.clustering_run_id")
    )
    algorithm_version: Mapped[str] = mapped_column(String(64))
    input_snapshot_hash: Mapped[str] = mapped_column(String(64))
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    run_status_code: Mapped[str] = mapped_column(String(32), default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "candidate_profile_version_id",
            "clustering_run_id",
            "algorithm_version",
            "input_snapshot_hash",
            name="uk_candidate_match_snapshot",
        ),
    )


class CandidateMatchResult(Base):
    __tablename__ = "biz_candidate_match_result"

    candidate_match_result_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    candidate_match_run_id: Mapped[int] = mapped_column(
        ForeignKey("biz_candidate_match_run.candidate_match_run_id")
    )
    result_code: Mapped[str] = mapped_column(String(64), unique=True)
    job_cluster_version_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_cluster_version.job_cluster_version_id")
    )
    representative_job_posting_id: Mapped[int | None] = mapped_column(
        ForeignKey("biz_job_posting.job_posting_id")
    )
    rank_no: Mapped[int] = mapped_column(Integer)
    overall_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    dimension_json: Mapped[list] = mapped_column(JSON)
    recommendation_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "candidate_match_run_id", "job_cluster_version_id", name="uk_match_cluster"
        ),
        Index("idx_match_result_rank", "candidate_match_run_id", "rank_no"),
    )


class CandidateMatchDimensionResult(Base):
    __tablename__ = "biz_match_dimension_result"

    match_dimension_result_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    candidate_match_result_id: Mapped[int] = mapped_column(
        ForeignKey("biz_candidate_match_result.candidate_match_result_id")
    )
    dimension_code: Mapped[str] = mapped_column(String(64))
    dimension_label: Mapped[str] = mapped_column(String(200))
    raw_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    weight: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    contribution: Mapped[Decimal] = mapped_column(Numeric(7, 4))
    status_code: Mapped[str] = mapped_column(String(32), default="scored")
    explanation_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "candidate_match_result_id", "dimension_code", name="uk_match_dimension_result"
        ),
        Index("idx_match_dimension_result", "candidate_match_result_id"),
    )


class CandidateMatchGap(Base):
    __tablename__ = "biz_candidate_match_gap"

    candidate_match_gap_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    candidate_match_result_id: Mapped[int] = mapped_column(
        ForeignKey("biz_candidate_match_result.candidate_match_result_id")
    )
    technology_node_id: Mapped[int] = mapped_column(
        ForeignKey("md_technology_node.technology_node_id")
    )
    gap_type_code: Mapped[str] = mapped_column(String(32))
    importance_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    candidate_evidence_json: Mapped[list] = mapped_column(JSON)
    job_evidence_json: Mapped[list] = mapped_column(JSON)
    transfer_from_technology_node_id: Mapped[int | None] = mapped_column(
        ForeignKey("md_technology_node.technology_node_id")
    )
    explanation_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "candidate_match_result_id", "technology_node_id", name="uk_match_gap_technology"
        ),
    )


class CandidateLearningPath(Base):
    __tablename__ = "biz_candidate_learning_path"

    candidate_learning_path_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    path_code: Mapped[str] = mapped_column(String(64), unique=True)
    candidate_match_result_id: Mapped[int] = mapped_column(
        ForeignKey("biz_candidate_match_result.candidate_match_result_id")
    )
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    algorithm_version: Mapped[str] = mapped_column(String(64))
    summary_text: Mapped[str] = mapped_column(Text)
    steps_json: Mapped[list] = mapped_column(JSON)
    workflow_status_code: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "candidate_match_result_id", "version_no", name="uk_learning_path_version"
        ),
    )
