"""导入「版本发布」类里程碑（补 T5 工程工具链域的成熟度证据）。

**为什么需要单独一条导入路径。** 现有 427 条里程碑全部来自旧实验库的 SQLite，
形态是论文/专利/产品发布这类「事件型」证据，集中在算法与硬件域。工程工具链域
（T5：操作系统 / 中间件 / 部署工具链 / 云边端）一条都没有——不是这些技术不重要，
恰恰相反，它们是招聘需求最高的方向（T5.03 单独就有 379 份 JD 提及），
而是它们的里程碑形态是**版本发布**，整理事件型里程碑时不会被收进来。

**日期精度是一等公民。** 版本发布日期是最容易被凭印象写错的一类事实，因此
变更集里每条都必须声明 `date_precision`，本工具据此决定落库形态：

- `day`   → event_date 落精确日期，data_origin = source_fact
- `month` → event_date 落当月 15 日（与「年份取年中」同一约定），标 estimated_date
- `year`  → event_date 留空，只落年份，标 estimated_date

成熟度按 exp(-0.35·年龄) 衰减，月级误差对贡献的影响约 3%，可接受；
但把只知道年份的事件写成精确日期会制造假精度，因此禁止。

用法（backend 目录 / 容器内）：
    python -m tools.import_release_milestones \\
        --changeset /srv/data/governance/xxx.json --dry-run
    python -m tools.import_release_milestones \\
        --changeset /srv/data/governance/xxx.json --auto-verify
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.data_center.models import MilestoneEvent, MilestoneTechnology
from app.modules.data_center.service import MilestoneSubmission, submit_milestone_candidate
from app.modules.taxonomy.models import TechnologyNode

SOURCE_CODE = "milestone_curated_lab"
# 只接受这几类——版本发布属于平台/开源/产品发布，不应混入论文专利。
ALLOWED_TYPES = {"platform_release", "open_source", "product_release", "standard_policy"}
ALLOWED_PRECISION = {"day", "month", "year"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导入版本发布类技术里程碑。")
    parser.add_argument("--changeset", type=Path, required=True)
    parser.add_argument("--collected-at", type=date.fromisoformat, default=date.today())
    parser.add_argument("--auto-verify", action="store_true")
    parser.add_argument("--verifier-code", default="admin-demo")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def resolve_event_date(item: dict) -> tuple[date | None, int, str]:
    """按声明的精度决定落库形态，返回 (event_date, event_year, data_origin_code)。"""
    precision = item["date_precision"]
    if precision not in ALLOWED_PRECISION:
        raise SystemExit(f"未知的日期精度：{precision}（{item['name']}）")
    parsed = date.fromisoformat(item["event_date"])
    if precision == "day":
        return parsed, parsed.year, "source_fact"
    if precision == "month":
        # 与「只知年份取年中」同一约定：只知月份就取月中，不伪造具体某一天。
        return date(parsed.year, parsed.month, 15), parsed.year, "estimated_date"
    return None, parsed.year, "estimated_date"


def validate(items: list[dict]) -> None:
    errors: list[str] = []
    seen: set[str] = set()
    for item in items:
        name = item.get("name", "<无名>")
        for field in ("name", "event_date", "date_precision", "technology_code", "milestone_type"):
            if not item.get(field):
                errors.append(f"{name}：缺少字段 {field}")
        if item.get("milestone_type") not in ALLOWED_TYPES:
            errors.append(f"{name}：里程碑类型 {item.get('milestone_type')} 不在允许集合内")
        if name in seen:
            errors.append(f"{name}：变更集内重复")
        seen.add(name)
        relevance = float(item.get("relevance", 1.0))
        if not 0 < relevance <= 1:
            errors.append(f"{name}：relevance 必须落在 (0, 1]")
    if errors:
        raise SystemExit("变更集校验失败：\n" + "\n".join(f"  - {item}" for item in errors))


def main() -> None:
    args = parse_args()
    payload = json.loads(args.changeset.read_text(encoding="utf-8"))
    items = payload["milestones"]
    validate(items)

    stats = {"导入": 0, "幂等命中": 0, "技术编码失配跳过": 0}
    precision_stats: dict[str, int] = {}
    collected_at = datetime.combine(args.collected_at, datetime.min.time())

    with SessionLocal() as session:
        imported_ids: list[int] = []
        for item in items:
            code = item["technology_code"]
            node = session.scalar(
                select(TechnologyNode.technology_node_id).where(
                    TechnologyNode.technology_code == code
                )
            )
            if node is None:
                stats["技术编码失配跳过"] += 1
                continue

            event_date, event_year, origin = resolve_event_date(item)
            precision_stats[item["date_precision"]] = (
                precision_stats.get(item["date_precision"], 0) + 1
            )
            if args.dry_run:
                stats["导入"] += 1
                continue

            name = item["name"].strip()[:500]
            # 证据引文必须能逐字定位，这里以「事实 + 判断依据」构成，
            # 依据字段保留了整理者当时凭什么下的判断，便于事后复核。
            quote = (
                f"{item['description']}\n"
                f"判断依据：{item.get('basis', '未记录')}\n"
                f"日期精度：{item['date_precision']}"
                f"（置信 {item.get('confidence', '未标注')}）"
            )
            submission = MilestoneSubmission(
                data_source_code=SOURCE_CODE,
                source_record_key=f"RELEASE-{name}",
                canonical_url=f"curated://embodied-job-evolution-lab/release/{code}/{name}",
                title=name[:1000],
                content_text=quote,
                published_at=None,
                collected_at=collected_at,
                milestone_name=name,
                milestone_type_code=item["milestone_type"],
                event_date=event_date,
                event_year=event_year,
                description_text=quote[:5000],
                maturity_delta_score=None,
                evidence_quote=quote,
                technology_codes=(code,),
                extractor_code="curated-release-milestone",
                extractor_version="1.0.0",
            )
            before = session.scalar(
                select(MilestoneEvent.milestone_event_id).where(
                    MilestoneEvent.milestone_name == name
                )
            )
            milestone = submit_milestone_candidate(session, submission)
            session.flush()
            if before is not None and before == milestone.milestone_event_id:
                stats["幂等命中"] += 1
            else:
                stats["导入"] += 1

            # 服务层把 relevance_score 固定写 100，按变更集声明的相关度还原。
            for relation in session.scalars(
                select(MilestoneTechnology).where(
                    MilestoneTechnology.milestone_event_id == milestone.milestone_event_id
                )
            ):
                relation.relevance_score = Decimal(
                    str(round(float(item.get("relevance", 1.0)) * 100, 2))
                )
            milestone.data_origin_code = origin
            imported_ids.append(milestone.milestone_event_id)

        if args.auto_verify and not args.dry_run:
            from tools.import_milestones import _bulk_verify

            stats["批量核实"] = _bulk_verify(session, imported_ids, args.verifier_code)
        if not args.dry_run:
            session.commit()

    print(json.dumps({**stats, "日期精度分布": precision_stats}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
