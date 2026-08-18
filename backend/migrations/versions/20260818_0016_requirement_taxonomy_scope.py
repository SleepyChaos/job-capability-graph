"""scope job requirements to a technology taxonomy version

技术词抽取原本只在 JD 导入时跑一次，`biz_job_requirement` 也没有词表版本维度，
于是词表升版后无法在既有 JD 上重新抽取——要么改不了，要么只能就地覆盖并毁掉
历史解析运行。补上 `taxonomy_version_id` 后，同一份 JD 可以同时持有 v1.1 与 v1.2
两套技术要求，历史 parse_run 仍能通过自己的词表版本读回原始口径。

存量行全部回填为当前唯一的 active 词表版本。

Revision ID: 20260818_0016
Revises: 20260814_0015
Create Date: 2026-08-18 09:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_0016"
down_revision: str | None = "20260814_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "biz_job_requirement",
        sa.Column("taxonomy_version_id", sa.BigInteger(), nullable=True),
    )
    bind = op.get_bind()
    # 存量抽取全部产自首个 active 词表版本（v1.1）；取最小 id 保证确定性。
    fallback_version_id = bind.scalar(
        sa.text(
            "SELECT MIN(taxonomy_version_id) FROM md_technology_taxonomy_version"
            " WHERE version_status_code = 'active'"
        )
    ) or bind.scalar(sa.text("SELECT MIN(taxonomy_version_id) FROM md_technology_taxonomy_version"))
    if fallback_version_id is not None:
        bind.execute(
            sa.text(
                "UPDATE biz_job_requirement SET taxonomy_version_id = :version_id"
                " WHERE taxonomy_version_id IS NULL"
            ),
            {"version_id": fallback_version_id},
        )
    else:
        # 空库（单测/全新环境）没有词表版本可回填，此时表内也不会有存量行。
        bind.execute(sa.text("DELETE FROM biz_job_requirement WHERE taxonomy_version_id IS NULL"))

    # MySQL 会拿唯一索引给外键当支撑索引。旧的两个唯一约束都以 job_posting_id 打头，
    # 而新约束以 taxonomy_version_id 打头，直接删旧约束会报「needed in a foreign key
    # constraint」。先补一个 job_posting_id 单列索引顶上，再做约束替换。
    with op.batch_alter_table("biz_job_requirement") as batch:
        batch.alter_column("taxonomy_version_id", existing_type=sa.BigInteger(), nullable=False)
        batch.create_index("idx_job_requirement_posting", ["job_posting_id"])
        batch.create_unique_constraint(
            "uk_job_requirement_version_no",
            ["taxonomy_version_id", "job_posting_id", "requirement_no"],
        )
        batch.create_unique_constraint(
            "uk_job_requirement_version_technology_type",
            [
                "taxonomy_version_id",
                "job_posting_id",
                "technology_node_id",
                "requirement_type_code",
            ],
        )
        batch.drop_constraint("uk_job_requirement_no", type_="unique")
        batch.drop_constraint("uk_job_requirement_technology_type", type_="unique")
        batch.create_foreign_key(
            "fk_job_requirement_taxonomy_version",
            "md_technology_taxonomy_version",
            ["taxonomy_version_id"],
            ["taxonomy_version_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("biz_job_requirement") as batch:
        batch.drop_constraint("fk_job_requirement_taxonomy_version", type_="foreignkey")
        batch.drop_index("idx_job_requirement_posting")
        batch.create_unique_constraint(
            "uk_job_requirement_no", ["job_posting_id", "requirement_no"]
        )
        batch.create_unique_constraint(
            "uk_job_requirement_technology_type",
            ["job_posting_id", "technology_node_id", "requirement_type_code"],
        )
        batch.drop_constraint("uk_job_requirement_version_no", type_="unique")
        batch.drop_constraint("uk_job_requirement_version_technology_type", type_="unique")
        batch.drop_column("taxonomy_version_id")
