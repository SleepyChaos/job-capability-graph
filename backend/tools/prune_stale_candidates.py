"""清理过期算法版本产出的候选提议。

**为什么会积。** 候选是持久实体，不是每轮的输出快照。每次推演只重算排名前
`max_communities`（默认 100）个技术组合：命中已有键的就地刷新，没命中的新建，
而**本轮没被提出的候选原样不动**——不删除、不标记、不重算。一个组合一旦掉出前
100 名，就再也没有运行会碰它，它带着当时那版算法算出的评分、分档、分类永久留在库里。
算法从 v1_5 走到 v1_12、词表从 v1.1 换到 v1.2，进入前 100 名的组合换了好几批，
于是「库里有多少候选」变成了历次运行的并集，而不是算法当前的结论。

**为什么必须清。** 不是因为陈旧候选会挡住新提议——去重按技术组合算键，不同组合
各自成候选，互不影响。真正的两条是：

1. **同名冲突**：不同技术组合可能拼出同一个名字，跨代同名会让审核者看到两条
   名字一样、评分与分类却不同的提议，无法判断该信哪个。
2. **终态永久生效**：候选一旦被审核者驳回或合并，`TERMINAL_CANDIDATE_STATUSES`
   会让该技术组合**永不再被提出**。若这个终态是对着过期算法的结论下的，那么算法
   改进之后，同一个组合再也没有机会以新面貌出现。这条目前还没发作，因为尚无人工
   审核记录，但它是清理必须在开始审核之前做完的理由。

**绝不删的四类。** 任何承载了人工判断或对外产出的候选都保留，哪怕它已过期——
过期的是评分，不是人的决定：

- 审核状态不是 `pending` / `needs_revision` 的（已批准、已合并、已驳回）
- 有任何审核动作记录的
- 已发布标准 JD 的
- 已关联正式岗位的

用法（backend 目录 / 容器内）：
    python -m tools.prune_stale_candidates                # 默认只看不删
    python -m tools.prune_stale_candidates --execute
"""

from __future__ import annotations

import argparse
import json
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.modules.data_center.models import ReviewAction, ReviewTask
from app.modules.discovery.models import (
    CandidateScoreComponent,
    CandidateTechnology,
    DiscoveryRun,
    EmergingRoleCandidate,
    StandardJobDescription,
)
from app.modules.discovery.service import ALGORITHM_VERSION

CANDIDATE_TARGET_TYPE = "emerging_role"
PRUNABLE_STATUSES = frozenset({"pending", "needs_revision"})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="清理过期算法版本产出的候选提议。")
    parser.add_argument(
        "--algorithm-version",
        default=ALGORITHM_VERSION,
        help=f"视为「当前」的算法版本，默认 {ALGORITHM_VERSION}",
    )
    parser.add_argument("--execute", action="store_true", help="真正删除（默认只统计）")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    return parser.parse_args()


def classify(db: Session, current_version: str) -> tuple[list, list, list]:
    """返回 (当前代, 可清理的陈旧候选, 因承载人工判断而保留的陈旧候选)。"""
    fresh_run_ids = set(
        db.scalars(
            select(DiscoveryRun.discovery_run_id).where(
                DiscoveryRun.algorithm_version == current_version
            )
        )
    )
    rows = list(db.scalars(select(EmergingRoleCandidate)))
    stale = [row for row in rows if row.last_seen_discovery_run_id not in fresh_run_ids]
    current = [row for row in rows if row.last_seen_discovery_run_id in fresh_run_ids]

    stale_ids = [row.emerging_role_candidate_id for row in stale]
    if not stale_ids:
        return current, [], []

    # 有审核动作的候选：人已经在上面留下过判断。
    acted = set(
        db.scalars(
            select(ReviewTask.target_id)
            .join(ReviewAction, ReviewAction.review_task_id == ReviewTask.review_task_id)
            .where(
                ReviewTask.target_type_code == CANDIDATE_TARGET_TYPE,
                ReviewTask.target_id.in_(stale_ids),
            )
        )
    )
    published = set(
        db.scalars(
            select(StandardJobDescription.emerging_role_candidate_id).where(
                StandardJobDescription.emerging_role_candidate_id.in_(stale_ids)
            )
        )
    )

    prunable, protected = [], []
    for row in stale:
        cid = row.emerging_role_candidate_id
        if (
            row.workflow_status_code not in PRUNABLE_STATUSES
            or cid in acted
            or cid in published
            or row.approved_job_role_id is not None
        ):
            protected.append(row)
        else:
            prunable.append(row)
    return current, prunable, protected


def delete(db: Session, doomed: list[int]) -> None:
    task_ids = list(
        db.scalars(
            select(ReviewTask.review_task_id).where(
                ReviewTask.target_type_code == CANDIDATE_TARGET_TYPE,
                ReviewTask.target_id.in_(doomed),
            )
        )
    )
    if task_ids:
        db.query(ReviewAction).filter(ReviewAction.review_task_id.in_(task_ids)).delete(
            synchronize_session=False
        )
        db.query(ReviewTask).filter(ReviewTask.review_task_id.in_(task_ids)).delete(
            synchronize_session=False
        )
    for model in (CandidateScoreComponent, CandidateTechnology, StandardJobDescription):
        db.query(model).filter(model.emerging_role_candidate_id.in_(doomed)).delete(
            synchronize_session=False
        )
    db.query(EmergingRoleCandidate).filter(
        EmergingRoleCandidate.emerging_role_candidate_id.in_(doomed)
    ).delete(synchronize_session=False)
    db.commit()


def main() -> None:
    args = parse_args()
    with SessionLocal() as session:
        total = session.scalar(select(func.count()).select_from(EmergingRoleCandidate))
        current, prunable, protected = classify(session, args.algorithm_version)

        summary = {
            "algorithm_version": args.algorithm_version,
            "candidate_total": total,
            "current_generation": len(current),
            "stale_prunable": len(prunable),
            "stale_protected": len(protected),
            "executed": bool(args.execute),
        }

        if args.format == "text":
            print(f"当前算法版本：{args.algorithm_version}")
            print(f"候选总数 {total} · 当前代 {len(current)} "
                  f"· 可清理 {len(prunable)} · 因人工判断保留 {len(protected)}")
            if prunable:
                print("\n可清理候选的分类分布：",
                      dict(Counter(row.classification_code for row in prunable)))
                llm = sum(
                    1
                    for row in prunable
                    if (row.expression_json or {}).get("generation_method") == "llm_expression"
                )
                print(f"其中带 LLM 表达层的：{llm}（删除会丢失这部分文案）")
            if protected:
                print("\n以下陈旧候选因承载人工判断而保留：")
                for row in protected[:10]:
                    print(f"   [{row.workflow_status_code}] {row.proposed_name}")

        if not args.execute:
            if args.format == "text":
                print("\n默认只统计不删除。确认后加 --execute 执行。")
            else:
                print(json.dumps(summary, ensure_ascii=False))
            return

        delete(session, [row.emerging_role_candidate_id for row in prunable])
        remaining = session.scalar(select(func.count()).select_from(EmergingRoleCandidate))
        summary["candidate_remaining"] = remaining
        if args.format == "json":
            print(json.dumps(summary, ensure_ascii=False))
        else:
            print(f"\n已删除 {len(prunable)} 个陈旧候选，剩余 {remaining} 个。")


if __name__ == "__main__":
    main()
