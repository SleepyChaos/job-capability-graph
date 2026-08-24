"""批量生成候选的表达层（LLM 命名与描述）。

**为什么需要。** 候选的 `proposed_name` 默认是机械名——把技术名拼起来加「工程师」。
它唯一、可追溯，但不是岗位名：「运动控制(通用)·电机与驱动工程师」读起来是两个技术
的并列，不是一个职位。真正的命名由表达层完成，而表达层此前只被逐个手工触发过，
实测 227 个候选里只有 2 个跑过 LLM，其余 225 个都停在机械降级上。

**机械事实不可变。** LLM 只能改写表达层（名称、定义、职责、形成原因、差异说明），
改不了任何机械事实——评分、分档、分类、技术组合、证据引用都由算法算出并固定。
这是 `llm_boundary: expression_only_no_fact_mutation` 的约束，服务层强制执行。

**默认只处理当前算法版本刷新过的候选。** 候选一次创建、永久保留，而每轮只重算前
100 个组合，名额之外的候选带着旧版评分留在库里。给陈旧候选生成表达层是在为过期
事实写文案，因此默认跳过；`--include-stale` 可覆盖。

用法（backend 目录 / 容器内）：
    python -m tools.generate_candidate_expressions --dry-run
    python -m tools.generate_candidate_expressions --limit 20
"""

from __future__ import annotations

import argparse
import json
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.infrastructure.llm import llm_available
from app.modules.discovery.models import DiscoveryRun, EmergingRoleCandidate
from app.modules.discovery.service import auto_candidate_expression

# 只有待审与待修改的候选允许改表达层，与服务层的约束一致。
ELIGIBLE_STATUSES = ("pending", "needs_revision")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量生成候选表达层。")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少个，0 为不限")
    parser.add_argument(
        "--include-stale",
        action="store_true",
        help="连同非当前算法版本刷新的候选一起处理（默认跳过）",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="连同已由 LLM 生成过的候选一起重做（默认只补机械降级的）",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def pick(db: Session, args: argparse.Namespace) -> list[EmergingRoleCandidate]:
    latest = db.scalar(select(DiscoveryRun).order_by(DiscoveryRun.discovery_run_id.desc()))
    rows = list(
        db.scalars(
            select(EmergingRoleCandidate)
            .where(EmergingRoleCandidate.workflow_status_code.in_(ELIGIBLE_STATUSES))
            .order_by(EmergingRoleCandidate.candidate_score.desc())
        )
    )
    if not args.include_stale and latest is not None:
        rows = [
            row for row in rows if row.last_seen_discovery_run_id == latest.discovery_run_id
        ]
    if not args.regenerate:
        rows = [
            row
            for row in rows
            if (row.expression_json or {}).get("generation_method") != "llm_expression"
        ]
    return rows[: args.limit] if args.limit else rows


def main() -> None:
    args = parse_args()
    if not llm_available() and not args.dry_run:
        raise SystemExit("LLM 网关无 API Key——全部调用会降级为规则输出，无需批量重跑")

    with SessionLocal() as session:
        targets = pick(session, args)
        print(f"待处理候选：{len(targets)}")
        if args.dry_run:
            for row in targets[:15]:
                print(f"  {float(row.candidate_score):5.1f}  {row.proposed_name}")
            return

        stats: Counter[str] = Counter()
        for index, row in enumerate(targets, start=1):
            before = row.proposed_name
            try:
                updated = auto_candidate_expression(session, candidate_code=row.candidate_code)
            except Exception as error:  # noqa: BLE001 —— 单个候选失败不该中断整批
                stats["失败"] += 1
                print(f"  [{index}/{len(targets)}] 失败 {before}：{error}")
                continue
            method = (updated.expression_json or {}).get("generation_method", "?")
            stats[method] += 1
            if method == "llm_expression":
                print(f"  [{index}/{len(targets)}] {before}\n{'':>22}→ {updated.proposed_name}")
        print(json.dumps(dict(stats), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
