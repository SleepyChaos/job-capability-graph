"""widen normalized job titles for MySQL imports

Revision ID: 20260812_0012
Revises: 20260811_0011
Create Date: 2026-08-12 14:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_0012"
down_revision: str | None = "20260811_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        # utf8mb4 VARCHAR(1000) cannot fit a full-length secondary index in
        # MySQL's 3072-byte limit; the title index only needs a searchable
        # prefix because published_at remains the second index dimension.
        op.drop_index("idx_job_title_time", table_name="biz_job_posting")
        op.alter_column(
            "biz_job_posting",
            "job_title_normalized",
            existing_type=sa.String(length=500),
            type_=sa.String(length=1000),
            existing_nullable=False,
        )
        op.create_index(
            "idx_job_title_time",
            "biz_job_posting",
            ["job_title_normalized", "published_at"],
            mysql_length={"job_title_normalized": 191},
        )
    else:
        with op.batch_alter_table("biz_job_posting") as batch:
            batch.alter_column(
                "job_title_normalized",
                existing_type=sa.String(length=500),
                type_=sa.String(length=1000),
                existing_nullable=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.drop_index("idx_job_title_time", table_name="biz_job_posting")
        op.alter_column(
            "biz_job_posting",
            "job_title_normalized",
            existing_type=sa.String(length=1000),
            type_=sa.String(length=500),
            existing_nullable=False,
        )
        op.create_index(
            "idx_job_title_time",
            "biz_job_posting",
            ["job_title_normalized", "published_at"],
        )
    else:
        with op.batch_alter_table("biz_job_posting") as batch:
            batch.alter_column(
                "job_title_normalized",
                existing_type=sa.String(length=1000),
                type_=sa.String(length=500),
                existing_nullable=False,
            )
