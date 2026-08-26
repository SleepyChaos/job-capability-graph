"""从技术里程碑事件中抽取 L3 技术点，产出与上游语料同格式的分片。

**为什么要单独走里程碑这条线。** 上游共现路径（论文与专利）的证据是「两个技术在
N 篇文献里一起出现过」，它有两处说不清：一是语料域偏离——arXiv 的 cs.RO 里无人机
研究占比很高，与中文具身智能招聘市场谈的不是一回事，「强化学习 + 无人机」这条
A 级缺口多半是这么来的；二是共现本身不指向任何具体事实，审阅者无从判断。

里程碑事件不同：它是**有日期、有类型、人工筛过**的具体事件（「它石智航 AWE 3.5
通用具身大模型发布」2026-07-17），锚点硬，也不会混进域外主题。代价是量小——
474 条，且名称平均 21 字、描述平均 42 字，技术密度远低于论文摘要。

**只取 `source_fact`。** 另有 56 条 `estimated_date` 与 12 条 `derived_date`，
它们的日期是推出来的而非事件本身携带的，其中多数被默认到 2026 年。锚点日期是本
分析的核心量，用推定日期会把信号系统性地拉到近期，宁可不要。

**输出格式与上游抽取一致**（`tech_YYYY.jsonl`，含 `published` 与 `technology_codes`），
因此 `find_upstream_only_pairs` 与候选构建工具可以直接读，判据只有一处实现。

用法（backend 目录 / 容器内）：
    python -m tools.extract_milestone_technologies --out /srv/data/upstream/milestone_extracted
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.taxonomy.models import TechnologyNode, TechnologyTaxonomyVersion
from tools.extract_upstream_technologies import build_alias_matcher

TOOL_VERSION = "milestone_extract_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从里程碑事件抽取 L3 技术点。")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--origins",
        default="source_fact",
        help="纳入的 data_origin_code。默认只取 source_fact——推定日期会污染锚点",
    )
    parser.add_argument(
        "--min-technologies",
        type=int,
        default=1,
        help="至少命中几个技术才写出。默认 1：单技术条目不产生技术对，"
        "但保留下来可用于统计覆盖情况",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    origins = {part.strip() for part in args.origins.split(",") if part.strip()}
    args.out.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as session:
        version_id = session.scalar(
            select(TechnologyTaxonomyVersion.taxonomy_version_id)
            .where(TechnologyTaxonomyVersion.version_status_code == "active")
            .order_by(TechnologyTaxonomyVersion.effective_date.desc())
            .limit(1)
        )
        matcher = build_alias_matcher(session, version_id)
        nodes = {
            node.technology_node_id: node
            for node in session.scalars(
                select(TechnologyNode).where(
                    TechnologyNode.taxonomy_version_id == version_id
                )
            )
        }
        # 里程碑模型定义在 maturity 模块，这里只读四个字段，用 Core 查询即可，
        # 免得为一处只读引入模块间依赖。
        from sqlalchemy import text

        rows = session.execute(
            text(
                "SELECT milestone_code, milestone_name, description_text, "
                "event_date, milestone_type_code, data_origin_code "
                "FROM biz_milestone_event ORDER BY event_date"
            )
        ).all()

    stats: Counter[str] = Counter()
    by_year: dict[str, list[dict]] = defaultdict(list)
    tech_counter: Counter[str] = Counter()
    for code, name, description, event_date, type_code, origin in rows:
        stats["读取"] += 1
        if origin not in origins:
            stats[f"{origin}，跳过"] += 1
            continue
        if not event_date:
            stats["无日期，跳过"] += 1
            continue
        blob = f"{name or ''} {description or ''}"
        codes = sorted(
            {
                nodes[hit.l3_technology_node_id].technology_code
                for hit in matcher.find(blob)
                if hit.l3_technology_node_id in nodes
            }
        )
        if len(codes) < args.min_technologies:
            stats["技术命中不足，跳过"] += 1
            continue
        tech_counter.update(codes)
        published = str(event_date)[:10]
        by_year[published[:4]].append(
            {
                # 复用上游分片的字段名，下游 load_upstream 按 published /
                # technology_codes 读取，无需为里程碑改动任何判据代码。
                "arxiv_id": code,
                "published": published,
                "technology_codes": codes,
                "milestone_name": name,
                "milestone_type_code": type_code,
            }
        )
        stats["纳入"] += 1
        if len(codes) >= 2:
            stats["命中≥2 个技术（可用于组合分析）"] += 1

    for year, items in sorted(by_year.items()):
        path = args.out / f"tech_{year}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for item in items:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    (args.out / "_manifest.json").write_text(
        json.dumps(
            {
                "tool_version": TOOL_VERSION,
                "source": "biz_milestone_event",
                "origins": sorted(origins),
                "anchor_field": "event_date（事件本身携带的日期）",
                "note": (
                    "里程碑名称平均 21 字、描述平均 42 字，技术密度远低于论文摘要；"
                    "本分片的价值在锚点可指到具体事件，不在数量"
                ),
                "totals": {
                    "read": stats["读取"],
                    "kept": stats["纳入"],
                    "multi_technology": stats["命中≥2 个技术（可用于组合分析）"],
                    "distinct_technologies": len(tech_counter),
                },
                "by_year": {year: len(items) for year, items in sorted(by_year.items())},
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )

    print(json.dumps(dict(stats), ensure_ascii=False, indent=2))
    print(f"\n涉及 L3 技术点 {len(tech_counter)} 个，写入 {args.out}")
    print("出现最多的技术点：")
    for code, count in tech_counter.most_common(8):
        print(f"   {code}  {count} 条里程碑")


if __name__ == "__main__":
    main()
