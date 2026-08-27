"""match dimension result

Revision ID: 20260811_0008
Revises: 20260811_0007
Create Date: 2026-08-11 23:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0008"
down_revision: str | None = "20260811_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "biz_match_dimension_result",
        sa.Column(
            "match_dimension_result_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "candidate_match_result_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=False,
        ),
        sa.Column("dimension_code", sa.String(length=64), nullable=False),
        sa.Column("dimension_label", sa.String(length=200), nullable=False),
        sa.Column("raw_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("weight", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("contribution", sa.Numeric(precision=7, scale=4), nullable=False),
        sa.Column("status_code", sa.String(length=32), nullable=False),
        sa.Column("explanation_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["candidate_match_result_id"],
            ["biz_candidate_match_result.candidate_match_result_id"],
            name=op.f(
                "fk_biz_match_dimension_result_candidate_match_result_id_biz_candidate_match_result"
            ),
        ),
        sa.PrimaryKeyConstraint(
            "match_dimension_result_id", name=op.f("pk_biz_match_dimension_result")
        ),
        sa.UniqueConstraint(
            "candidate_match_result_id", "dimension_code", name="uk_match_dimension_result"
        ),
    )
    op.create_index(
        "idx_match_dimension_result",
        "biz_match_dimension_result",
        ["candidate_match_result_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_match_dimension_result", table_name="biz_match_dimension_result")
    op.drop_table("biz_match_dimension_result")
