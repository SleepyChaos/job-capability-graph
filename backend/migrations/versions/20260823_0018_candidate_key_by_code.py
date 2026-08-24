"""rebuild candidate_key from technology codes and merge the duplicates it exposed

Revision ID: 20260823_0018
Revises: 20260820_0017
Create Date: 2026-08-23 12:00:00.000000

`candidate_key` 原先由技术**节点 id** 计算。节点 id 逐词表版本独立，同一个技术
组合在 v1.1 与 v1.2 下拿到不同 id，键因此不同，去重失效——同一组技术被当成两个
候选反复提出。实测 227 个候选里有 43 组、共 105 个条目属于这种重复，而且重复条目
之间的分类还会互相矛盾（同名候选一个判 existing_role、一个判 role_evolution），
因为它们各自在不同版本的词表下算过覆盖率。

本迁移做两件事：按技术编码重算全部 candidate_key，并把因此暴露出来的重复合并。

**保留谁。** 按优先级取一个保留，其余删除：

1. 表达层是 LLM 生成的（`generation_method == 'llm_expression'`）——LLM 产出不能丢
2. 已被人工处置的（`workflow_status_code` 非 `pending`）——人工结论不能丢
3. 评分最高的
4. id 最大的（最后创建）

**为什么可以删。** 被删的条目与保留者技术编码集完全相同，是同一个候选的重复登记，
不是不同的候选。落库当时 227 个候选全部处于 `pending`，没有任何人工结论会因此丢失；
若日后重跑时该情形不再成立，第 1、2 条优先级会把有产出的那一条留下来。

审核任务经 `(target_type_code, target_id)` 软引用候选，且 `(queue_code,
target_type_code, target_id)` 唯一——保留者已有自己的任务，被删条目的任务无法改指
到保留者上（会撞唯一约束），只能一并删除。
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260823_0018"
down_revision: str | None = "20260820_0017"
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

    codes_by_candidate: dict[int, list[str]] = defaultdict(list)
    for cid, code in bind.execute(
        sa.text(
            """
            SELECT rct.emerging_role_candidate_id, t.technology_code
              FROM rel_candidate_technology rct
              JOIN md_technology_node t
                ON t.technology_node_id = rct.technology_node_id
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
            # 没有技术组合的候选无法计算稳定身份，保持原键不动。
            continue
        key = candidate_key(row["mode_code"], codes)
        grouped[key].append({
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
        keeper, losers = members[0], members[1:]
        doomed.extend(item["cid"] for item in losers)
        bind.execute(
            sa.text(
                "UPDATE biz_emerging_role_candidate SET candidate_key = :key"
                " WHERE emerging_role_candidate_id = :cid"
            ),
            {"key": key, "cid": keeper["cid"]},
        )

    if not doomed:
        return

    # 唯一约束在 candidate_key 上，被删条目仍持有旧键；先逐个清空成一次性占位值，
    # 避免删除前的中间状态与保留者撞键。
    for cid in doomed:
        bind.execute(
            sa.text(
                "UPDATE biz_emerging_role_candidate SET candidate_key = :key"
                " WHERE emerging_role_candidate_id = :cid"
            ),
            {"key": f"merged-{cid:d}".ljust(40, "0")[:64], "cid": cid},
        )

    for table, column in (
        ("biz_candidate_score_component", "emerging_role_candidate_id"),
        ("rel_candidate_technology", "emerging_role_candidate_id"),
        ("biz_standard_job_description", "emerging_role_candidate_id"),
    ):
        bind.execute(
            sa.text(f"DELETE FROM {table} WHERE {column} IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
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
            "DELETE FROM biz_review_task"
            " WHERE target_type_code = :tt AND target_id IN :ids"
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
    """把键退回按节点 id 计算。

    **被合并掉的重复条目不还原**——它们是同一候选的重复登记，删除即丢失。
    回退只恢复键的算法，不恢复数据；需要那些条目就得从备份恢复或重跑推演。
    """
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT c.emerging_role_candidate_id AS cid, r.mode_code AS mode_code
              FROM biz_emerging_role_candidate c
              JOIN biz_role_discovery_run r
                ON r.discovery_run_id = c.discovery_run_id
            """
        )
    ).mappings().all()
    nodes_by_candidate: dict[int, list[int]] = defaultdict(list)
    for cid, node_id in bind.execute(
        sa.text(
            "SELECT emerging_role_candidate_id, technology_node_id"
            "  FROM rel_candidate_technology"
        )
    ):
        nodes_by_candidate[cid].append(node_id)
    for row in rows:
        nodes = nodes_by_candidate.get(row["cid"])
        if not nodes:
            continue
        payload = f"{row['mode_code']}|" + "-".join(str(item) for item in sorted(nodes))
        bind.execute(
            sa.text(
                "UPDATE biz_emerging_role_candidate SET candidate_key = :key"
                " WHERE emerging_role_candidate_id = :cid"
            ),
            {"key": hashlib.sha256(payload.encode()).hexdigest()[:64], "cid": row["cid"]},
        )
