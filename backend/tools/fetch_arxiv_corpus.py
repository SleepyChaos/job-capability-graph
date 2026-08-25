"""抓取 arXiv 论文摘要，作为「比 JD 更早」的上游语料。

**它要回答的问题。** 岗位 = 雇主把一组能力打包成一个招聘需求。要在岗位出现**前**
发现它，必须看雇主在招人**之前**干了什么——研发、论文、专利。若两个技术在上游
反复一起出现，却没有任何一份 JD 把它们写进同一个岗位，那就是一个还没走到招聘
环节的能力组合。见《16-上游语料与领先性验证任务书》。

**为什么是论文而不是继续用里程碑。** 现有 474 条里程碑里 317 条只挂 1 个技术点，
L2 口径只产出 9 个技术对，而 JD 侧有 438 个——差两个数量级，撑不起共现分析。
论文天然在一篇里提及多个技术，这正是共现分析需要的密度。

**发表日期是干净的时间轴。** 采集时间 ≠ 发布时间 ≠ 岗位出现时间，JD 侧的时间
不可靠；而论文的 `published` 是文档自带属性，不是采集产物。领先性回测因此只切
上游的时间轴，JD 整体当作「现在」的快照——一个 JD 时间戳都不需要。

**只落原始文档，不做抽取。** 抽取依赖英文别名覆盖率（当前仅 17%，见任务 U-1），
补完别名后重跑抽取即可，不必重抓。抓取与抽取分离，抓一次可以反复抽。

用法（backend 目录 / 容器内）：
    python -m tools.fetch_arxiv_corpus --categories cs.RO --from-year 2024 --per-year 20 --dry-run
    python -m tools.fetch_arxiv_corpus --categories cs.RO,cs.AI,cs.LG,cs.CV \\
        --from-year 2019 --per-year 400 --out /srv/data/upstream/arxiv
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from xml.etree import ElementTree

ARXIV_API = "http://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"
# arXiv 要求调用之间至少间隔 3 秒，这是它的服务条款，不是性能调优。
REQUEST_INTERVAL_SECONDS = 3.0
PAGE_SIZE = 100


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="抓取 arXiv 摘要作为上游语料。")
    parser.add_argument(
        "--categories",
        default="cs.RO",
        help="arXiv 分类，逗号分隔。具身智能相关：cs.RO 机器人 / cs.AI / cs.LG / cs.CV",
    )
    parser.add_argument("--from-year", type=int, default=2019, help="起始年份")
    parser.add_argument("--to-year", type=int, default=date.today().year, help="结束年份")
    parser.add_argument(
        "--per-year",
        type=int,
        default=400,
        help="每个分类每年抓多少篇。**必须按年分层抽样**，见 fetch_year 的说明",
    )
    parser.add_argument("--out", type=Path, help="输出目录；省略则只统计不落盘")
    parser.add_argument("--dry-run", action="store_true", help="只抓第一页看看结构")
    return parser.parse_args()


def normalise(text: str | None) -> str:
    """arXiv 的摘要带换行与多余空白，压平以便后续做字符串匹配。"""
    return re.sub(r"\s+", " ", (text or "")).strip()


def fetch_page(category: str, year: int, start: int, page_size: int) -> list[dict]:
    """取某分类某一年的一页结果。

    **必须带年份区间。** 首版实现按提交时间倒序整体抓、每类封顶 N 篇，结果 8,452 篇
    论文**全部落在同一年**——arXiv 每个分类几个月就发这么多，倒序抓只能回溯几个月。
    而领先性回测的整个设计是按 T = 2020…2025 切上游语料，没有跨年覆盖就无从做起。
    因此改为逐年用 submittedDate 区间查询，每年抽固定篇数，得到时间上均衡的样本。
    """
    window = f"[{year}01010000 TO {year}12312359]"
    query = urllib.parse.urlencode({
        "search_query": f"cat:{category} AND submittedDate:{window}",
        "start": start,
        "max_results": page_size,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })
    request = urllib.request.Request(
        f"{ARXIV_API}?{query}",
        headers={"User-Agent": "embodied-job-graph/1.0 (research; contact via repo)"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        root = ElementTree.fromstring(response.read())

    papers = []
    for entry in root.findall(f"{ATOM}entry"):
        published = entry.findtext(f"{ATOM}published") or ""
        arxiv_id = (entry.findtext(f"{ATOM}id") or "").rsplit("/", 1)[-1]
        if not arxiv_id or not published:
            continue
        papers.append({
            "arxiv_id": arxiv_id,
            # 发表日期是文档自带属性，不是采集产物——这是回测唯一可信的时间轴。
            "published": published[:10],
            "updated": (entry.findtext(f"{ATOM}updated") or "")[:10],
            "title": normalise(entry.findtext(f"{ATOM}title")),
            "abstract": normalise(entry.findtext(f"{ATOM}summary")),
            "categories": [
                node.get("term") for node in entry.findall(f"{ATOM}category")
            ],
            "primary_category": category,
        })
    return papers


def fetch_year(category: str, year: int, limit: int, dry_run: bool) -> list[dict]:
    collected: list[dict] = []
    seen: set[str] = set()
    start = 0
    while len(collected) < limit:
        page = fetch_page(category, year, start, min(PAGE_SIZE, limit - len(collected)))
        if not page:
            break
        for paper in page:
            if paper["arxiv_id"] in seen:
                continue
            seen.add(paper["arxiv_id"])
            collected.append(paper)
        if dry_run or len(page) < PAGE_SIZE:
            break
        start += PAGE_SIZE
        time.sleep(REQUEST_INTERVAL_SECONDS)
    return collected


def main() -> None:
    args = parse_args()
    categories = [item.strip() for item in args.categories.split(",") if item.strip()]

    everything: dict[str, dict] = {}
    first = True
    for category in categories:
        for year in range(args.from_year, args.to_year + 1):
            if not first:
                time.sleep(REQUEST_INTERVAL_SECONDS)
            first = False
            rows = fetch_year(category, year, args.per_year, args.dry_run)
            print(f"  {category} {year}: {len(rows)} 篇")
            for paper in rows:
                # 一篇论文可能同时属于多个分类，按 arXiv id 去重。
                everything.setdefault(paper["arxiv_id"], paper)

    papers = sorted(everything.values(), key=lambda item: item["published"], reverse=True)
    years: dict[str, int] = {}
    for paper in papers:
        years[paper["published"][:4]] = years.get(paper["published"][:4], 0) + 1

    print(f"\n去重后共 {len(papers)} 篇")
    print("按年份分布：")
    for year in sorted(years):
        print(f"   {year}: {years[year]}")

    if args.dry_run:
        for paper in papers[:3]:
            print(f"\n  [{paper['published']}] {paper['title'][:80]}")
            print(f"    {paper['abstract'][:160]}…")
        return

    if not args.out:
        return
    args.out.mkdir(parents=True, exist_ok=True)
    # 按年分片：回测要按时点切语料，分年存可以只读需要的片段。
    by_year: dict[str, list[dict]] = {}
    for paper in papers:
        by_year.setdefault(paper["published"][:4], []).append(paper)
    for year, rows in sorted(by_year.items()):
        path = args.out / f"arxiv_{year}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"  写入 {path.name}：{len(rows)} 篇")
    (args.out / "_manifest.json").write_text(
        json.dumps(
            {
                "categories": categories,
                "from_year": args.from_year,
                "to_year": args.to_year,
                "per_year": args.per_year,
                "fetched_at": date.today().isoformat(),
                "paper_count": len(papers),
                "by_year": years,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
