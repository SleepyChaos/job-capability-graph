"""scope job scenarios to their parse run

场景是解析运行的派生物，但 rel_job_scenario 的唯一约束只有
(job_posting_id, scenario_no)，导致同一批 JD 的第二次解析必然主键冲突。
补上 job_parse_run_id 后与 biz_job_responsibility 的运行隔离方式一致。

Revision ID: 20260814_0014
Revises: 20260812_0013
Create Date: 2026-08-14 08:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260814_0014"
down_revision: str | None = "20260812_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUN_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.add_column("rel_job_scenario", sa.Column("job_parse_run_id", RUN_ID, nullable=True))
    # 存量场景归属到该 JD 当时唯一的那次解析运行；无解析结果的孤儿行直接清理。
    op.get_bind().execute(
        sa.text(
            "UPDATE rel_job_scenario SET job_parse_run_id = ("
            " SELECT MIN(r.job_parse_run_id) FROM rel_job_parse_result r"
            " WHERE r.job_posting_id = rel_job_scenario.job_posting_id)"
        )
    )
    op.get_bind().execute(sa.text("DELETE FROM rel_job_scenario WHERE job_parse_run_id IS NULL"))
    with op.batch_alter_table("rel_job_scenario") as batch:
        batch.alter_column("job_parse_run_id", existing_type=RUN_ID, nullable=False)
        # 先建新唯一约束再删旧的：MySQL 上旧索引被 job_posting_id 外键占用，
        # 顺序反过来会报 "needed in a foreign key constraint"。
        batch.create_unique_constraint(
            "uk_job_scenario_run_no", ["job_parse_run_id", "job_posting_id", "scenario_no"]
        )
        batch.drop_constraint("uk_job_scenario_no", type_="unique")
        batch.create_foreign_key(
            "fk_job_scenario_parse_run",
            "biz_job_parse_run",
            ["job_parse_run_id"],
            ["job_parse_run_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("rel_job_scenario") as batch:
        batch.create_unique_constraint("uk_job_scenario_no", ["job_posting_id", "scenario_no"])
        batch.drop_constraint("fk_job_scenario_parse_run", type_="foreignkey")
        batch.drop_constraint("uk_job_scenario_run_no", type_="unique")
        batch.drop_column("job_parse_run_id")
