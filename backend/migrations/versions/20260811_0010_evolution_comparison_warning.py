"""evolution comparison warning

Revision ID: 20260811_0010
Revises: 20260811_0009
Create Date: 2026-08-12 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0010"
down_revision: str | None = "20260811_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "biz_job_evolution_event",
        sa.Column("comparison_warning_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("biz_job_evolution_event", "comparison_warning_text")
