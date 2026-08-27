"""add JD parsing and clustering feature preparation

Revision ID: 20260811_0003
Revises: 20260811_0002
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0003"
down_revision: str | None = "20260811_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def pk_type():
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "biz_job_parse_run",
        sa.Column("job_parse_run_id", pk_type(), nullable=False),
        sa.Column("run_code", sa.String(length=64), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("taxonomy_version_id", pk_type(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("input_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("run_status_code", sa.String(length=32), nullable=False),
        sa.Column("input_job_count", sa.Integer(), nullable=False),
        sa.Column("parsed_job_count", sa.Integer(), nullable=False),
        sa.Column("review_job_count", sa.Integer(), nullable=False),
        sa.Column("responsibility_count", sa.Integer(), nullable=False),
        sa.Column("assessment_count", sa.Integer(), nullable=False),
        sa.Column("feature_count", sa.Integer(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["taxonomy_version_id"],
            ["md_technology_taxonomy_version.taxonomy_version_id"],
            name=op.f(
                "fk_biz_job_parse_run_taxonomy_version_id_md_technology_taxonomy_version"
            ),
        ),
        sa.PrimaryKeyConstraint("job_parse_run_id", name=op.f("pk_biz_job_parse_run")),
        sa.UniqueConstraint("run_code", name=op.f("uq_biz_job_parse_run_run_code")),
    )
    op.create_index(
        "idx_job_parse_run_status",
        "biz_job_parse_run",
        ["run_status_code", "target_date"],
        unique=False,
    )
    op.create_table(
        "md_technology_ambiguity_rule",
        sa.Column("technology_ambiguity_rule_id", pk_type(), nullable=False),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("normalized_alias", sa.String(length=500), nullable=False),
        sa.Column("technology_node_id", pk_type(), nullable=False),
        sa.Column("positive_markers_json", sa.JSON(), nullable=False),
        sa.Column("missing_context_decision_code", sa.String(length=32), nullable=False),
        sa.Column("review_weight", sa.Numeric(precision=7, scale=4), nullable=False),
        sa.Column("rule_version", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["technology_node_id"],
            ["md_technology_node.technology_node_id"],
            name=op.f(
                "fk_md_technology_ambiguity_rule_technology_node_id_md_technology_node"
            ),
        ),
        sa.PrimaryKeyConstraint(
            "technology_ambiguity_rule_id", name=op.f("pk_md_technology_ambiguity_rule")
        ),
        sa.UniqueConstraint(
            "normalized_alias", "technology_node_id", name="uk_ambiguity_alias_technology"
        ),
        sa.UniqueConstraint(
            "rule_code", name=op.f("uq_md_technology_ambiguity_rule_rule_code")
        ),
    )
    op.create_index(
        "idx_ambiguity_rule_active",
        "md_technology_ambiguity_rule",
        ["is_active", "normalized_alias"],
        unique=False,
    )
    op.create_table(
        "rel_job_parse_result",
        sa.Column("job_parse_run_id", pk_type(), nullable=False),
        sa.Column("job_posting_id", pk_type(), nullable=False),
        sa.Column("source_document_version_id", pk_type(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("parse_status_code", sa.String(length=32), nullable=False),
        sa.Column("responsibility_count", sa.Integer(), nullable=False),
        sa.Column("required_segment_count", sa.Integer(), nullable=False),
        sa.Column("bonus_segment_count", sa.Integer(), nullable=False),
        sa.Column("unknown_segment_count", sa.Integer(), nullable=False),
        sa.Column("ambiguity_review_count", sa.Integer(), nullable=False),
        sa.Column("parse_quality_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("review_required", sa.Boolean(), nullable=False),
        sa.Column("reason_json", sa.JSON(), nullable=True),
        sa.Column(
            "parsed_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_parse_run_id"],
            ["biz_job_parse_run.job_parse_run_id"],
            name=op.f("fk_rel_job_parse_result_job_parse_run_id_biz_job_parse_run"),
        ),
        sa.ForeignKeyConstraint(
            ["job_posting_id"],
            ["biz_job_posting.job_posting_id"],
            name=op.f("fk_rel_job_parse_result_job_posting_id_biz_job_posting"),
        ),
        sa.ForeignKeyConstraint(
            ["source_document_version_id"],
            ["raw_source_document_version.source_document_version_id"],
            name=op.f(
                "fk_rel_job_parse_result_source_document_version_id_raw_source_document_version"
            ),
        ),
        sa.PrimaryKeyConstraint(
            "job_parse_run_id", "job_posting_id", name=op.f("pk_rel_job_parse_result")
        ),
    )
    op.create_index(
        "idx_job_parse_result_quality",
        "rel_job_parse_result",
        ["job_parse_run_id", "parse_quality_score"],
        unique=False,
    )
    op.create_index(
        "idx_job_parse_result_review",
        "rel_job_parse_result",
        ["job_parse_run_id", "review_required"],
        unique=False,
    )
    op.create_table(
        "biz_job_responsibility",
        sa.Column("job_responsibility_id", pk_type(), nullable=False),
        sa.Column("job_parse_run_id", pk_type(), nullable=False),
        sa.Column("job_posting_id", pk_type(), nullable=False),
        sa.Column("responsibility_no", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("normalized_task_text", sa.Text(), nullable=True),
        sa.Column("action_verb", sa.String(length=100), nullable=True),
        sa.Column("task_object", sa.String(length=500), nullable=True),
        sa.Column("expected_output", sa.String(length=500), nullable=True),
        sa.Column("extraction_method_code", sa.String(length=64), nullable=False),
        sa.Column("confidence_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_parse_run_id"],
            ["biz_job_parse_run.job_parse_run_id"],
            name=op.f("fk_biz_job_responsibility_job_parse_run_id_biz_job_parse_run"),
        ),
        sa.ForeignKeyConstraint(
            ["job_posting_id"],
            ["biz_job_posting.job_posting_id"],
            name=op.f("fk_biz_job_responsibility_job_posting_id_biz_job_posting"),
        ),
        sa.PrimaryKeyConstraint(
            "job_responsibility_id", name=op.f("pk_biz_job_responsibility")
        ),
        sa.UniqueConstraint(
            "job_parse_run_id",
            "job_posting_id",
            "responsibility_no",
            name="uk_job_responsibility_run_no",
        ),
    )
    op.create_index(
        "idx_job_responsibility_job",
        "biz_job_responsibility",
        ["job_posting_id", "job_parse_run_id"],
        unique=False,
    )
    op.create_table(
        "biz_job_cluster_feature_snapshot",
        sa.Column("job_parse_run_id", pk_type(), nullable=False),
        sa.Column("job_posting_id", pk_type(), nullable=False),
        sa.Column("feature_version", sa.String(length=64), nullable=False),
        sa.Column("title_tokens_json", sa.JSON(), nullable=False),
        sa.Column("responsibility_tokens_json", sa.JSON(), nullable=False),
        sa.Column("technology_weights_json", sa.JSON(), nullable=False),
        sa.Column("domain_weights_json", sa.JSON(), nullable=False),
        sa.Column("level_code", sa.String(length=32), nullable=True),
        sa.Column("sample_weight", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("time_quality_code", sa.String(length=32), nullable=False),
        sa.Column("feature_hash", sa.String(length=64), nullable=False),
        sa.Column("eligible_for_clustering", sa.Boolean(), nullable=False),
        sa.Column("exclusion_reason_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_parse_run_id"],
            ["biz_job_parse_run.job_parse_run_id"],
            name=op.f(
                "fk_biz_job_cluster_feature_snapshot_job_parse_run_id_biz_job_parse_run"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["job_posting_id"],
            ["biz_job_posting.job_posting_id"],
            name=op.f(
                "fk_biz_job_cluster_feature_snapshot_job_posting_id_biz_job_posting"
            ),
        ),
        sa.PrimaryKeyConstraint(
            "job_parse_run_id",
            "job_posting_id",
            name=op.f("pk_biz_job_cluster_feature_snapshot"),
        ),
    )
    op.create_index(
        "idx_cluster_feature_eligible",
        "biz_job_cluster_feature_snapshot",
        ["job_parse_run_id", "eligible_for_clustering", "time_quality_code"],
        unique=False,
    )
    op.create_table(
        "biz_technology_match_assessment",
        sa.Column("technology_match_assessment_id", pk_type(), nullable=False),
        sa.Column("job_parse_run_id", pk_type(), nullable=False),
        sa.Column("job_requirement_id", pk_type(), nullable=False),
        sa.Column("evidence_span_id", pk_type(), nullable=False),
        sa.Column("context_evidence_span_id", pk_type(), nullable=True),
        sa.Column("ambiguity_rule_id", pk_type(), nullable=True),
        sa.Column("context_type_code", sa.String(length=32), nullable=False),
        sa.Column("assessment_status_code", sa.String(length=32), nullable=False),
        sa.Column("adjusted_support_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("feature_weight", sa.Numeric(precision=7, scale=4), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column(
            "assessed_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ambiguity_rule_id"],
            ["md_technology_ambiguity_rule.technology_ambiguity_rule_id"],
            name=op.f(
                "fk_biz_technology_match_assessment_ambiguity_rule_id_md_technology_ambiguity_rule"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["context_evidence_span_id"],
            ["biz_evidence_span.evidence_span_id"],
            name=op.f(
                "fk_biz_technology_match_assessment_context_evidence_span_id_biz_evidence_span"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["evidence_span_id"],
            ["biz_evidence_span.evidence_span_id"],
            name=op.f(
                "fk_biz_technology_match_assessment_evidence_span_id_biz_evidence_span"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["job_parse_run_id"],
            ["biz_job_parse_run.job_parse_run_id"],
            name=op.f(
                "fk_biz_technology_match_assessment_job_parse_run_id_biz_job_parse_run"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["job_requirement_id"],
            ["biz_job_requirement.job_requirement_id"],
            name=op.f(
                "fk_biz_technology_match_assessment_job_requirement_id_biz_job_requirement"
            ),
        ),
        sa.PrimaryKeyConstraint(
            "technology_match_assessment_id",
            name=op.f("pk_biz_technology_match_assessment"),
        ),
        sa.UniqueConstraint(
            "job_parse_run_id",
            "job_requirement_id",
            "evidence_span_id",
            name="uk_match_assessment_run_evidence",
        ),
    )
    op.create_index(
        "idx_match_assessment_review",
        "biz_technology_match_assessment",
        ["job_parse_run_id", "assessment_status_code", "reason_code"],
        unique=False,
    )
    op.create_table(
        "rel_job_fact_evidence",
        sa.Column("job_fact_evidence_id", pk_type(), nullable=False),
        sa.Column("job_parse_run_id", pk_type(), nullable=False),
        sa.Column("job_posting_id", pk_type(), nullable=False),
        sa.Column("target_type_code", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column("evidence_span_id", pk_type(), nullable=False),
        sa.Column("support_type_code", sa.String(length=32), nullable=False),
        sa.Column("support_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.ForeignKeyConstraint(
            ["evidence_span_id"],
            ["biz_evidence_span.evidence_span_id"],
            name=op.f("fk_rel_job_fact_evidence_evidence_span_id_biz_evidence_span"),
        ),
        sa.ForeignKeyConstraint(
            ["job_parse_run_id"],
            ["biz_job_parse_run.job_parse_run_id"],
            name=op.f("fk_rel_job_fact_evidence_job_parse_run_id_biz_job_parse_run"),
        ),
        sa.ForeignKeyConstraint(
            ["job_posting_id"],
            ["biz_job_posting.job_posting_id"],
            name=op.f("fk_rel_job_fact_evidence_job_posting_id_biz_job_posting"),
        ),
        sa.PrimaryKeyConstraint(
            "job_fact_evidence_id", name=op.f("pk_rel_job_fact_evidence")
        ),
        sa.UniqueConstraint(
            "job_parse_run_id",
            "target_type_code",
            "target_id",
            "evidence_span_id",
            "support_type_code",
            name="uk_job_fact_evidence_run",
        ),
    )


def downgrade() -> None:
    op.drop_table("rel_job_fact_evidence")
    op.drop_index("idx_match_assessment_review", table_name="biz_technology_match_assessment")
    op.drop_table("biz_technology_match_assessment")
    op.drop_index("idx_cluster_feature_eligible", table_name="biz_job_cluster_feature_snapshot")
    op.drop_table("biz_job_cluster_feature_snapshot")
    op.drop_index("idx_job_responsibility_job", table_name="biz_job_responsibility")
    op.drop_table("biz_job_responsibility")
    op.drop_index("idx_job_parse_result_review", table_name="rel_job_parse_result")
    op.drop_index("idx_job_parse_result_quality", table_name="rel_job_parse_result")
    op.drop_table("rel_job_parse_result")
    op.drop_index("idx_ambiguity_rule_active", table_name="md_technology_ambiguity_rule")
    op.drop_table("md_technology_ambiguity_rule")
    op.drop_index("idx_job_parse_run_status", table_name="biz_job_parse_run")
    op.drop_table("biz_job_parse_run")
