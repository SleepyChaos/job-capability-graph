"""从 arXiv 摘要抽取技术点，产出带发表日期的技术共现记录。

抓取与抽取分离：`fetch_arxiv_corpus.py` 只落原始文档，本工具负责抽取。这样别名
覆盖率提升后重抽即可，不必重抓——v1.2 时英文覆盖率只有 17%，v1.3 补到 91%，
正是这条分界带来的好处。

**与 JD 侧共用同一个匹配器。** `build_alias_matcher()` 是 JD 抽取用的那一个，
不另起一套：两侧的技术识别口径必须一致，否则「上游有、JD 没有」这个判断就可能
只是两套匹配规则的差异，而不是真实的时间差。

**产物是按年分片的技术集合，不是共现对。** 共现对该用多大的窗口、要不要限制在
同一 L2 内，是回测要试的参数，抽取阶段不替它决定。

用法（backend 目录 / 容器内）：
    python -m tools.extract_upstream_technologies \\
        --corpus /srv/data/upstream/arxiv --taxonomy-version v1.3 \\
        --out /srv/data/upstream/extracted
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.job.extraction_service import build_alias_matcher
from app.modules.taxonomy.models import TechnologyNode, TechnologyTaxonomyVersion


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从上游语料抽取技术点。")
    parser.add_argument("--corpus", type=Path, required=True, help="fetch_arxiv_corpus 的输出目录")
    parser.add_argument("--taxonomy-version", default="v1.3")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--min-technologies",
        type=int,
        default=2,
        help="少于该数量技术点的文档不计入。共现分析里单技术文档没有信息量",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    shards = sorted(args.corpus.glob("arxiv_*.jsonl"))
    if not shards:
        raise SystemExit(f"{args.corpus} 下没有 arxiv_*.jsonl，先跑 fetch_arxiv_corpus")

    with SessionLocal() as session:
        version_id = session.scalar(
            select(TechnologyTaxonomyVersion.taxonomy_version_id).where(
                TechnologyTaxonomyVersion.version_code == args.taxonomy_version
            )
        )
        if version_id is None:
            raise SystemExit(f"词表版本不存在：{args.taxonomy_version}")
        matcher = build_alias_matcher(session, version_id)
        code_by_node = {
            node_id: code
            for node_id, code in session.execute(
                select(TechnologyNode.technology_node_id, TechnologyNode.technology_code).where(
                    TechnologyNode.taxonomy_version_id == version_id
                )
            )
        }

    args.out.mkdir(parents=True, exist_ok=True)
    totals = Counter()
    per_year: dict[str, dict[str, int]] = {}

    for shard in shards:
        year = shard.stem.split("_")[-1]
        kept = []
        doc_count = 0
        tech_counter: Counter[str] = Counter()
        for line in shard.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            paper = json.loads(line)
            doc_count += 1
            # 标题与摘要一起匹配：标题里的技术词往往是论文的主题，不该漏掉。
            text = f"{paper['title']}. {paper['abstract']}"
            codes = sorted({
                code_by_node[hit.l3_technology_node_id]
                for hit in matcher.find(text)
                if hit.l3_technology_node_id in code_by_node
            })
            if len(codes) < args.min_technologies:
                continue
            tech_counter.update(codes)
            kept.append({
                "arxiv_id": paper["arxiv_id"],
                # 发表日期原样带出——它是回测唯一可信的时间轴。
                "published": paper["published"],
                "technology_codes": codes,
            })

        path = args.out / f"tech_{year}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for row in kept:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        density = sum(len(r["technology_codes"]) for r in kept) / len(kept) if kept else 0
        per_year[year] = {
            "documents": doc_count,
            "kept": len(kept),
            "distinct_technologies": len(tech_counter),
            "mean_technologies_per_kept_doc": round(density, 2),
        }
        totals["documents"] += doc_count
        totals["kept"] += len(kept)
        print(
            f"  {year}: {doc_count} 篇 → 命中 ≥{args.min_technologies} 个技术点的 {len(kept)} 篇"
            f"（{len(kept) / doc_count:.0%}），平均 {density:.2f} 个技术点"
        )

    manifest = {
        "taxonomy_version": args.taxonomy_version,
        "min_technologies": args.min_technologies,
        "totals": dict(totals),
        "by_year": per_year,
    }
    (args.out / "_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\n共 {totals['documents']} 篇，保留 {totals['kept']} 篇可用于共现分析")


if __name__ == "__main__":
    main()
