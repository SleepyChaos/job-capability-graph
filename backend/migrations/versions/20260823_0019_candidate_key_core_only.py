"""correct 0018: build candidate_key from the core combination only

Revision ID: 20260823_0019
Revises: 20260823_0018
Create Date: 2026-08-23 14:00:00.000000

修正 20260823_0018 的一处遗漏。

0018 按技术编码重算 `candidate_key`，编码取自 `rel_candidate_technology` 全表。
但该表同时存放**核心组合**与**画像层**两类技术（`membership_code` 为 core / profile，
实测 471 / 167），而线上 `_candidate_key` 只用核心组合。两边口径不一致，凡是带画像层
技术的候选，迁移写入的键与线上算出的键都对不上——下一次推演认不出它们，于是重新建了
一批候选，候选数从 165 反弹到 205。

本迁移用 `membership_code = 'core'` 过滤后重算，并把因此再次暴露的重复合并。
保留策略与 0018 相同：LLM 表达 > 已人工处置 > 评分高 > 后创建。
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260823_0019"
down_revision: str | None = "20260823_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CANDIDATE_TARGET_TYPE = "emerging_role"


def candidate_key(mode_code: str, technology_codes: Sequence[str]) -> str:
    """与 `discovery/service.py::_candidate_key` 保持同一算法。"""
    payload = f"{mode_code}|" + "-".join(sorted(technology_codes))
    return hashlib.sha256(payload.encode()).hexdigest()[:64]


def upgrade() -> None:
    bind = op.get_bind()

    rows = bind.execute(
        sa.text(
            """
            SELECT c.emerging_role_candidate_id AS cid,
                   r.mode_code                  AS mode_code,
                   c.candidate_score            AS score,
                   c.workflow_status_code       AS status,
                   c.expression_json            AS expression
              FROM biz_emerging_role_candidate c
              JOIN biz_role_discovery_run r
                ON r.discovery_run_id = c.discovery_run_id
            """
        )
    ).mappings().all()
    if not rows:
        return

    # 只取核心组合——画像层是核心之上扩展出来的展示用技术，不构成候选身份。
    codes_by_candidate: dict[int, list[str]] = defaultdict(list)
    for cid, code in bind.execute(
        sa.text(
            """
            SELECT rct.emerging_role_candidate_id, t.technology_code
              FROM rel_candidate_technology rct
              JOIN md_technology_node t
                ON t.technology_node_id = rct.technology_node_id
             WHERE rct.membership_code = 'core'
            """
        )
    ):
        codes_by_candidate[cid].append(code)

    def generation_method(raw) -> str:
        if not raw:
            return ""
        payload = json.loads(raw) if isinstance(raw, str) else raw
        return (payload or {}).get("generation_method", "")

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        codes = codes_by_candidate.get(row["cid"])
        if not codes:
            continue
        grouped[candidate_key(row["mode_code"], codes)].append({
            "cid": row["cid"],
            "score": float(row["score"] or 0),
            "status": row["status"],
            "llm": generation_method(row["expression"]) == "llm_expression",
        })

    doomed: list[int] = []
    for key, members in grouped.items():
        members.sort(
            key=lambda item: (
                item["llm"],
                item["status"] != "pending",
                item["score"],
                item["cid"],
            ),
            reverse=True,
        )
        doomed.extend(item["cid"] for item in members[1:])
        # 先把败者的键挪开，避免保留者写入时撞上唯一约束。
        for loser in members[1:]:
            bind.execute(
                sa.text(
                    "UPDATE biz_emerging_role_candidate SET candidate_key = :key"
                    " WHERE emerging_role_candidate_id = :cid"
                ),
                {"key": f"merged-{loser['cid']:d}".ljust(40, "0")[:64], "cid": loser["cid"]},
            )
        bind.execute(
            sa.text(
                "UPDATE biz_emerging_role_candidate SET candidate_key = :key"
                " WHERE emerging_role_candidate_id = :cid"
            ),
            {"key": key, "cid": members[0]["cid"]},
        )

    if not doomed:
        return

    for table in (
        "biz_candidate_score_component",
        "rel_candidate_technology",
        "biz_standard_job_description",
    ):
        bind.execute(
            sa.text(
                f"DELETE FROM {table} WHERE emerging_role_candidate_id IN :ids"
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": doomed},
        )
    bind.execute(
        sa.text(
            "DELETE FROM biz_review_action WHERE review_task_id IN ("
            "  SELECT review_task_id FROM biz_review_task"
            "   WHERE target_type_code = :tt AND target_id IN :ids)"
        ).bindparams(sa.bindparam("ids", expanding=True)),
        {"tt": CANDIDATE_TARGET_TYPE, "ids": doomed},
    )
    bind.execute(
        sa.text(
            "DELETE FROM biz_review_task WHERE target_type_code = :tt AND target_id IN :ids"
        ).bindparams(sa.bindparam("ids", expanding=True)),
        {"tt": CANDIDATE_TARGET_TYPE, "ids": doomed},
    )
    bind.execute(
        sa.text(
            "DELETE FROM biz_emerging_role_candidate"
            " WHERE emerging_role_candidate_id IN :ids"
        ).bindparams(sa.bindparam("ids", expanding=True)),
        {"ids": doomed},
    )


def downgrade() -> None:
    """无操作。

    0018 的 downgrade 已把键退回按节点 id 计算，本迁移只是修正 0018 写入的值，
    没有独立的回退目标；合并掉的重复条目同样不还原。
    """
