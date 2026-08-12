"""job scenario and data origin code

Revision ID: 20260811_0011
Revises: 20260811_0010
Create Date: 2026-08-12 01:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0011"
down_revision: str | None = "20260811_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rel_job_scenario",
        sa.Column(
            "job_scenario_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "job_posting_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=False,
        ),
        sa.Column("scenario_no", sa.Integer(), nullable=False),
        sa.Column("scenario_text", sa.Text(), nullable=False),
        sa.Column("normalized_scenario", sa.String(length=500), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("confidence_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("data_origin_code", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_posting_id"],
            ["biz_job_posting.job_posting_id"],
            name=op.f("fk_rel_job_scenario_job_posting_id_biz_job_posting"),
        ),
        sa.PrimaryKeyConstraint("job_scenario_id", name=op.f("pk_rel_job_scenario")),
        sa.UniqueConstraint("job_posting_id", "scenario_no", name="uk_job_scenario_no"),
    )
    op.create_index(
        "idx_job_scenario_posting", "rel_job_scenario", ["job_posting_id"], unique=False
    )
    # 统一数据来源标记（后端设计 §3.3）：source_fact / algorithm_inference /
    # llm_generated / human_confirmed。
    with op.batch_alter_table("biz_job_posting") as batch:
        batch.add_column(
            sa.Column(
                "data_origin_code",
                sa.String(length=32),
                nullable=False,
                server_default="source_fact",
            )
        )
    with op.batch_alter_table("biz_milestone_event") as batch:
        batch.add_column(
            sa.Column(
                "data_origin_code",
                sa.String(length=32),
                nullable=False,
                server_default="source_fact",
            )
        )
    with op.batch_alter_table("biz_standard_job_description") as batch:
        batch.add_column(
            sa.Column(
                "data_origin_code",
                sa.String(length=32),
                nullable=False,
                server_default="algorithm_inference",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("biz_standard_job_description") as batch:
        batch.drop_column("data_origin_code")
    with op.batch_alter_table("biz_milestone_event") as batch:
        batch.drop_column("data_origin_code")
    with op.batch_alter_table("biz_job_posting") as batch:
        batch.drop_column("data_origin_code")
    op.drop_index("idx_job_scenario_posting", table_name="rel_job_scenario")
    op.drop_table("rel_job_scenario")
