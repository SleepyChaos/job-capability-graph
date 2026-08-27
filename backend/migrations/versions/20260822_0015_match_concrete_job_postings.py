"""match concrete active job postings instead of cluster representatives

Revision ID: 20260822_0015
Revises: 20260819_0014
Create Date: 2026-08-22 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_0015"
down_revision: str | None = "20260819_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("biz_candidate_match_result") as batch_op:
        batch_op.drop_constraint("uk_match_cluster", type_="unique")
        batch_op.alter_column(
            "job_cluster_version_id",
            existing_type=sa.BigInteger(),
            nullable=True,
        )
        batch_op.create_unique_constraint(
            "uk_match_posting",
            ["candidate_match_run_id", "representative_job_posting_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("biz_candidate_match_result") as batch_op:
        batch_op.drop_constraint("uk_match_posting", type_="unique")
        batch_op.alter_column(
            "job_cluster_version_id",
            existing_type=sa.BigInteger(),
            nullable=False,
        )
        batch_op.create_unique_constraint(
            "uk_match_cluster",
            ["candidate_match_run_id", "job_cluster_version_id"],
        )
