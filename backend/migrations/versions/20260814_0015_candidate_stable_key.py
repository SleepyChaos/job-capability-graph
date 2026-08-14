"""give emerging role candidates a stable identity key

每次推演都会为同一技术组合新建一行候选，导致候选库里出现大量同名重复项。
补上由「推演模式 + 技术组合」派生的稳定键后，后续运行可以复用既有候选：
终态（已批准/已合并/已驳回）直接跳过，未决状态就地刷新。

Revision ID: 20260814_0015
Revises: 20260814_0014
Create Date: 2026-08-14 09:55:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260814_0015"
down_revision: str | None = "20260814_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "biz_emerging_role_candidate",
        sa.Column("candidate_key", sa.String(length=64), nullable=True),
    )
    # 存量候选无法反推技术组合口径，用各自唯一的 candidate_code 占位；
    # 新键为 sha256 十六进制，不会与占位值冲突，因此存量行只会被视为独立候选。
    op.get_bind().execute(
        sa.text(
            "UPDATE biz_emerging_role_candidate"
            " SET candidate_key = candidate_code WHERE candidate_key IS NULL"
        )
    )
    with op.batch_alter_table("biz_emerging_role_candidate") as batch:
        batch.alter_column("candidate_key", existing_type=sa.String(length=64), nullable=False)
        batch.create_unique_constraint("uk_emerging_candidate_key", ["candidate_key"])


def downgrade() -> None:
    with op.batch_alter_table("biz_emerging_role_candidate") as batch:
        batch.drop_constraint("uk_emerging_candidate_key", type_="unique")
        batch.drop_column("candidate_key")
