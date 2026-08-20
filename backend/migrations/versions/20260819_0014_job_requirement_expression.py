"""add versioned executable job requirement expressions

Revision ID: 20260819_0014
Revises: 20260812_0013
Create Date: 2026-08-19 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260819_0014"
down_revision: str | None = "20260812_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def pk_type():
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "biz_job_requirement_expression",
        sa.Column(
            "job_requirement_expression_id",
            pk_type(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("job_cluster_version_id", pk_type(), nullable=False),
        sa.Column("expression_version_no", sa.Integer(), nullable=False),
        sa.Column("expression_json", sa.JSON(), nullable=False),
        sa.Column("workflow_status_code", sa.String(length=32), nullable=False),
        sa.Column("source_type_code", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_cluster_version_id"],
            ["biz_job_cluster_version.job_cluster_version_id"],
        ),
        sa.PrimaryKeyConstraint("job_requirement_expression_id"),
        sa.UniqueConstraint(
            "job_cluster_version_id",
            "expression_version_no",
            name="uk_job_requirement_expression_version",
        ),
    )
    op.create_index(
        "idx_job_requirement_expression_status",
        "biz_job_requirement_expression",
        ["job_cluster_version_id", "workflow_status_code"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_job_requirement_expression_status",
        table_name="biz_job_requirement_expression",
    )
    op.drop_table("biz_job_requirement_expression")
