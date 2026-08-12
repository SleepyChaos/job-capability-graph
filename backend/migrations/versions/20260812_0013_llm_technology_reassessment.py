"""add audited LLM technology reassessment

Revision ID: 20260812_0013
Revises: 20260812_0012
Create Date: 2026-08-12 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_0013"
down_revision: str | None = "20260812_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def pk_type():
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "biz_llm_technology_reassessment_run",
        sa.Column("reassessment_run_id", pk_type(), autoincrement=True, nullable=False),
        sa.Column("run_code", sa.String(length=64), nullable=False),
        sa.Column("job_parse_run_id", pk_type(), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("input_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("run_status_code", sa.String(length=32), nullable=False),
        sa.Column("input_assessment_count", sa.Integer(), nullable=False),
        sa.Column("processed_count", sa.Integer(), nullable=False),
        sa.Column("accepted_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("uncertain_count", sa.Integer(), nullable=False),
        sa.Column("validation_failure_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["job_parse_run_id"], ["biz_job_parse_run.job_parse_run_id"]
        ),
        sa.PrimaryKeyConstraint("reassessment_run_id"),
        sa.UniqueConstraint("run_code"),
    )
    op.create_index(
        "idx_llm_technology_reassessment_run",
        "biz_llm_technology_reassessment_run",
        ["job_parse_run_id", "run_status_code"],
    )
    op.create_table(
        "biz_llm_technology_reassessment",
        sa.Column("reassessment_id", pk_type(), autoincrement=True, nullable=False),
        sa.Column("reassessment_run_id", pk_type(), nullable=False),
        sa.Column("technology_match_assessment_id", pk_type(), nullable=False),
        sa.Column("original_status_code", sa.String(length=32), nullable=False),
        sa.Column("decision_code", sa.String(length=32), nullable=False),
        sa.Column("confidence_score", sa.Numeric(precision=7, scale=6), nullable=True),
        sa.Column("evidence_quote", sa.Text(), nullable=True),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column("raw_response_json", sa.JSON(), nullable=True),
        sa.Column("validation_status_code", sa.String(length=32), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["reassessment_run_id"],
            ["biz_llm_technology_reassessment_run.reassessment_run_id"],
        ),
        sa.ForeignKeyConstraint(
            ["technology_match_assessment_id"],
            ["biz_technology_match_assessment.technology_match_assessment_id"],
        ),
        sa.PrimaryKeyConstraint("reassessment_id"),
        sa.UniqueConstraint(
            "reassessment_run_id",
            "technology_match_assessment_id",
            name="uk_llm_technology_reassessment_item",
        ),
    )
    op.create_index(
        "idx_llm_technology_reassessment_decision",
        "biz_llm_technology_reassessment",
        ["reassessment_run_id", "decision_code", "validation_status_code"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_llm_technology_reassessment_decision",
        table_name="biz_llm_technology_reassessment",
    )
    op.drop_table("biz_llm_technology_reassessment")
    op.drop_index(
        "idx_llm_technology_reassessment_run",
        table_name="biz_llm_technology_reassessment_run",
    )
    op.drop_table("biz_llm_technology_reassessment_run")
