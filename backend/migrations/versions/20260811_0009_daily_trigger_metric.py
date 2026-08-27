"""daily trigger metric

Revision ID: 20260811_0009
Revises: 20260811_0008
Create Date: 2026-08-12 00:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0009"
down_revision: str | None = "20260811_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "biz_technology_daily_trigger_metric",
        sa.Column(
            "technology_daily_trigger_metric_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=False,
        ),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("technology_domain_code", sa.String(length=8), nullable=False),
        sa.Column("technology_node_id", sa.Integer(), nullable=False),
        sa.Column("trigger_document_count", sa.Integer(), nullable=False),
        sa.Column("trigger_mention_count", sa.Integer(), nullable=False),
        sa.Column("independent_org_count", sa.Integer(), nullable=False),
        sa.Column("independent_source_count", sa.Integer(), nullable=False),
        sa.Column("clustering_run_code", sa.String(length=64), nullable=False),
        sa.Column("calculation_version", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "technology_daily_trigger_metric_id",
            name=op.f("pk_biz_technology_daily_trigger_metric"),
        ),
        sa.UniqueConstraint(
            "metric_date",
            "technology_domain_code",
            "technology_node_id",
            "clustering_run_code",
            name="uk_daily_trigger_metric",
        ),
    )
    op.create_index(
        "idx_daily_trigger_metric_run",
        "biz_technology_daily_trigger_metric",
        ["clustering_run_code", "metric_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_daily_trigger_metric_run", table_name="biz_technology_daily_trigger_metric"
    )
    op.drop_table("biz_technology_daily_trigger_metric")
