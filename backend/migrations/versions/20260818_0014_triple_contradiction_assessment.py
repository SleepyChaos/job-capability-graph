"""Layer C triple contradiction audit table.

Revision ID: 20260818_0014
Revises: 20260812_0013
Create Date: 2026-08-18 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260818_0014"
down_revision: str | None = "20260812_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def pk_type():
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    json_type = mysql.JSON()
    op.create_table(
        "biz_triple_contradiction_assessment",
        sa.Column("triple_contradiction_assessment_id", pk_type(), autoincrement=True, nullable=False),
        sa.Column("audit_run_code", sa.String(length=64), nullable=False),
        sa.Column("audit_model", sa.String(length=32), nullable=False, server_default="composite_v1"),
        sa.Column("sample_scope", sa.String(length=16), nullable=False, server_default="top_200"),
        sa.Column("subject_kind", sa.String(length=24), nullable=False),
        sa.Column("subject_id", sa.String(length=64), nullable=False),
        sa.Column("subject_label", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("predicate", sa.String(length=32), nullable=False),
        sa.Column("object_kind", sa.String(length=24), nullable=False),
        sa.Column("object_id", sa.String(length=64), nullable=False),
        sa.Column("object_label", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("plausibility_score", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("plausibility_level", sa.String(length=16), nullable=False),
        sa.Column("rule_flags", json_type, nullable=False),
        sa.Column("component_scores", json_type, nullable=False),
        sa.Column("review_status_code", sa.String(length=24), nullable=False, server_default="pending_review"),
        sa.Column("reviewer_code", sa.String(length=64), nullable=True),
        sa.Column("review_note_text", sa.Text(), nullable=True),
        sa.Column("evidence_summary_json", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("triple_contradiction_assessment_id"),
        sa.UniqueConstraint(
            "audit_run_code", "subject_id", "predicate", "object_id",
            name="uk_triple_audit_key",
        ),
    )
    op.create_index(
        "idx_triple_audit_run",
        "biz_triple_contradiction_assessment",
        ["audit_run_code", "plausibility_level"],
    )
    op.create_index(
        "idx_triple_audit_subject",
        "biz_triple_contradiction_assessment",
        ["subject_id"],
    )
    op.create_index(
        "idx_triple_audit_object",
        "biz_triple_contradiction_assessment",
        ["object_id"],
    )
    op.create_index(
        "idx_triple_audit_status",
        "biz_triple_contradiction_assessment",
        ["review_status_code"],
    )
    op.create_index(
        "idx_triple_audit_score",
        "biz_triple_contradiction_assessment",
        ["plausibility_score"],
    )


def downgrade() -> None:
    op.drop_index("idx_triple_audit_score", table_name="biz_triple_contradiction_assessment")
    op.drop_index("idx_triple_audit_status", table_name="biz_triple_contradiction_assessment")
    op.drop_index("idx_triple_audit_object", table_name="biz_triple_contradiction_assessment")
    op.drop_index("idx_triple_audit_subject", table_name="biz_triple_contradiction_assessment")
    op.drop_index("idx_triple_audit_run", table_name="biz_triple_contradiction_assessment")
    op.drop_table("biz_triple_contradiction_assessment")
