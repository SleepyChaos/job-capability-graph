"""track which discovery run last refreshed each candidate

Revision ID: 20260823_0020
Revises: 20260823_0019
Create Date: 2026-08-23 15:00:00.000000

候选是**一次创建、永久保留**的，而每次推演只重算排名前 `max_communities`（默认 100）
的技术组合。排在名额之外的候选会一直留在库里，带着产出它们的那一版算法算出的评分、
分档与分类——实测 183 个候选里有 105 个的评分分量仍来自更早的算法版本，其中还包括
一个已被删除的维度（technology_relevance）。

这个信息此前只存在于 `mechanical_card_json.last_seen_run_code`，埋在 JSON 里，
既不能索引也不便过滤，结果是前台会把新旧两代候选混在一起展示，实验脚本也得靠
解析 JSON 才能区分。提成真列后，"这个候选是不是当前算法算出来的" 变成可查询的事实。

不删除陈旧候选：它们承载着表达层产出与审核任务，删掉会丢失人工与 LLM 的工作成果。
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260823_0020"
down_revision: str | None = "20260823_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("biz_emerging_role_candidate") as batch:
        batch.add_column(
            sa.Column(
                "last_seen_discovery_run_id",
                sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
                nullable=True,
            )
        )

    bind = op.get_bind()
    runs = {
        code: run_id
        for run_id, code in bind.execute(
            sa.text("SELECT discovery_run_id, run_code FROM biz_role_discovery_run")
        )
    }
    rows = bind.execute(
        sa.text(
            "SELECT emerging_role_candidate_id, discovery_run_id, mechanical_card_json"
            "  FROM biz_emerging_role_candidate"
        )
    ).all()
    for cid, origin_run_id, raw in rows:
        card = json.loads(raw) if isinstance(raw, str) else (raw or {})
        # 卡片里没有 last_seen 的是本列引入之前、且从未被刷新过的候选，
        # 退回它们的创建运行——那确实是最后一次为它们计算评分的运行。
        run_id = runs.get((card or {}).get("last_seen_run_code"), origin_run_id)
        bind.execute(
            sa.text(
                "UPDATE biz_emerging_role_candidate SET last_seen_discovery_run_id = :rid"
                " WHERE emerging_role_candidate_id = :cid"
            ),
            {"rid": run_id, "cid": cid},
        )

    with op.batch_alter_table("biz_emerging_role_candidate") as batch:
        batch.alter_column(
            "last_seen_discovery_run_id",
            existing_type=sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=False,
        )
        batch.create_index(
            "idx_candidate_last_seen_run", ["last_seen_discovery_run_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("biz_emerging_role_candidate") as batch:
        batch.drop_index("idx_candidate_last_seen_run")
        batch.drop_column("last_seen_discovery_run_id")
