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
    python -m tools.fetch_arxiv_corpus --categories cs.RO --from 2020-01 --max 200 --dry-run
    python -m tools.fetch_arxiv_corpus --categories cs.RO,cs.AI --from 2019-01 --max 6000 \\
        --out /srv/data/upstream/arxiv
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime
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
    parser.add_argument("--from", dest="date_from", default="2019-01", help="起始年月 YYYY-MM")
    parser.add_argument("--max", type=int, default=1000, help="每个分类最多抓多少篇")
    parser.add_argument("--out", type=Path, help="输出目录；省略则只统计不落盘")
    parser.add_argument("--dry-run", action="store_true", help="只抓第一页看看结构")
    return parser.parse_args()


def month_start(value: str) -> date:
    year, month = value.split("-")
    return date(int(year), int(month), 1)


def normalise(text: str | None) -> str:
    """arXiv 的摘要带换行与多余空白，压平以便后续做字符串匹配。"""
    return re.sub(r"\s+", " ", (text or "")).strip()


def fetch_page(category: str, start: int, page_size: int) -> list[dict]:
    query = urllib.parse.urlencode({
        "search_query": f"cat:{category}",
        "start": start,
        "max_results": page_size,
        # 按提交时间倒序：先拿到最近的，中断也能得到一段完整的近期语料。
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
                node.get("term")
                for node in entry.findall("{http://arxiv.org/schemas/atom}primary_category")
            ] + [node.get("term") for node in entry.findall(f"{ATOM}category")],
            "primary_category": category,
        })
    return papers


def fetch_category(category: str, cutoff: date, limit: int, dry_run: bool) -> list[dict]:
    collected: list[dict] = []
    seen: set[str] = set()
    start = 0
    while len(collected) < limit:
        page = fetch_page(category, start, min(PAGE_SIZE, limit - len(collected)))
        if not page:
            break
        stop = False
        for paper in page:
            if paper["arxiv_id"] in seen:
                continue
            if datetime.strptime(paper["published"], "%Y-%m-%d").date() < cutoff:
                # 结果按提交时间倒序，一旦越过起始月就不必再往下翻。
                stop = True
                break
            seen.add(paper["arxiv_id"])
            collected.append(paper)
        print(f"  {category}: 已收集 {len(collected)} 篇")
        if stop or dry_run or len(page) < PAGE_SIZE:
            break
        start += PAGE_SIZE
        time.sleep(REQUEST_INTERVAL_SECONDS)
    return collected


def main() -> None:
    args = parse_args()
    cutoff = month_start(args.date_from)
    categories = [item.strip() for item in args.categories.split(",") if item.strip()]

    everything: dict[str, dict] = {}
    for index, category in enumerate(categories):
        if index:
            time.sleep(REQUEST_INTERVAL_SECONDS)
        for paper in fetch_category(category, cutoff, args.max, args.dry_run):
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
                "date_from": args.date_from,
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
