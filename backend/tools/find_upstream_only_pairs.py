"""找出「研究侧已成形、招聘侧未出现」的技术组合，并给出参考出现区间。

**这不是「全新岗位预测」。** 产出的是能力组合，不是岗位；给出的区间来自外部文献
先验，不是本系统的测量。命名与措辞必须守住这条界线——U-3 回测已经明确否掉了
「上游领先招聘若干年」这个命题（提升度不随时点前移下降），任何形如「该岗位将于 X
出现」的说法都没有依据。

## 三道噪声过滤，判据都是统计量而非拍出来的阈值

朴素地取「上游共现、JD 未共现」会捞进大量噪声。实测 88 对里约一半属于以下三类，
每类对应一道过滤：

**一、JD 侧漏检伪装成缺口。** 强化学习 + 目标检测在 JD 里几乎必然同时出现，
它之所以「未共现」，更可能是抽取漏了一侧（JD 抽取的受限口径 F1 只有 0.505）。
判据用**独立性下的期望共现数**：若两个技术各自在 JD 中常见，独立假设预测它们
本应共现若干次而实测为 0，这个「0」才是有信息的；若期望本就不足 1 次，
没共现说明不了任何事。这与领先性回测里对照臂用的是同一个零假设。

**二、同族近义对。** 无人机 + 飞行器(通用) 属于同一个 L2，是同一件事的两种说法，
不构成「跨领域的能力组合」。判据：两个技术必须分属不同 L2。

**三、语料域偏离。** arXiv 的 cs.RO 含大量无人机与低空研究，而本项目的 JD 语料是
具身智能岗位。判据：两个技术都必须在 JD 语料中**单独出现过足够多次**——市场上
根本不招的方向，其研究侧共现与本项目无关。这一条已被第一道的期望共现数蕴含，
但单独设一个下限更直观，也让被滤掉的原因可读。

## 参考区间

锚点取**两个技术首次在上游共现的时间**——这是论文对「技术突破信号首现」的定义，
比先前用的「成熟度跨过 θ」更贴合，且是真实日期而非模型构造。区间 = 锚点 +
该技术组合类型的传导时滞先验（算法类 10–15 月、系统集成类 12–18 月、
硬件类 15–24 月，另乘类型修正系数），复用 `estimate_transmission_lag`。

**先验不是测量。** 本项目 JD 侧的时间跨度仅约 10 周且为采集时间而非发布时间，
测不出 10–24 个月量级的时滞，因此区间可用但无法在本系统内验证；而 U-3 回测
进一步表明本项目数据不支持「上游领先招聘」这一前提本身。两条都要随结果一并声明。

用法（backend 目录 / 容器内）：
    python -m tools.find_upstream_only_pairs --extracted /srv/data/upstream/extracted
    python -m tools.find_upstream_only_pairs --extracted ... --min-cooccurrence 3 --format json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import date
from itertools import combinations
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.db.session import SessionLocal
from app.modules.clustering.models import JobClusteringRun
from app.modules.discovery.algorithm import estimate_transmission_lag
from app.modules.job.models import JobRequirement, TechnologyMatchAssessment
from app.modules.taxonomy.models import TechnologyNode

TOOL_VERSION = "upstream_only_pairs_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="找出研究侧已成形、招聘侧未出现的技术组合。")
    parser.add_argument("--extracted", type=Path, required=True)
    parser.add_argument(
        "--min-cooccurrence", type=int, default=5, help="上游共现多少次才纳入"
    )
    parser.add_argument(
        "--min-expected-jd",
        type=float,
        default=2.0,
        help="独立性下 JD 期望共现数的下限。低于它时「未共现」不具信息量",
    )
    parser.add_argument(
        "--min-jd-mentions",
        type=int,
        default=3,
        help="两个技术各自在 JD 中至少被提及多少份，才认为市场确实在招这个方向",
    )
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    return parser.parse_args()


def load_jd() -> tuple[dict[int, set[str]], Counter[str]]:
    with SessionLocal() as db:
        run = db.scalar(
            select(JobClusteringRun)
            .where(JobClusteringRun.run_status_code == "success")
            .order_by(JobClusteringRun.clustering_run_id.desc())
        )
        if run is None:
            raise SystemExit("不存在成功的聚类运行")
        node = aliased(TechnologyNode)
        rows = db.execute(
            select(JobRequirement.job_posting_id, node.technology_code)
            .join(node, node.technology_node_id == JobRequirement.technology_node_id)
            .join(
                TechnologyMatchAssessment,
                TechnologyMatchAssessment.job_requirement_id
                == JobRequirement.job_requirement_id,
            )
            .where(
                TechnologyMatchAssessment.job_parse_run_id == run.job_parse_run_id,
                TechnologyMatchAssessment.assessment_status_code == "accepted",
            )
            .distinct()
        ).all()
    by_job: dict[int, set[str]] = defaultdict(set)
    for job_id, code in rows:
        by_job[job_id].add(code)
    mentions: Counter[str] = Counter()
    for codes in by_job.values():
        mentions.update(codes)
    return by_job, mentions


def load_upstream(directory: Path) -> dict[tuple[str, str], list[str]]:
    """每个技术对在上游的全部共现日期，升序。

    保留完整日期序列而不是只留首次——锚点该取「共现累积到门槛的那一刻」，
    即这个组合在研究侧**站住脚**的时间，而不是第一次偶然同现。首次共现往往在多年
    之前，用它当锚点会让参考区间落在过去，对一个至今未进入招聘的组合而言，
    那既不是预测也说不通。
    """
    dates: dict[tuple[str, str], list[str]] = defaultdict(list)
    for shard in sorted(directory.glob("tech_*.jsonl")):
        for line in shard.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            codes = sorted(set(row["technology_codes"]))
            for pair in combinations(codes, 2):
                dates[pair].append(row["published"])
    return {pair: sorted(days) for pair, days in dates.items()}


def shift_month(anchor: str, months: int) -> str:
    year, month = int(anchor[:4]), int(anchor[5:7])
    total = month - 1 + months
    return f"{year + total // 12:04d}-{total % 12 + 1:02d}"


def main() -> None:
    args = parse_args()
    up_dates = load_upstream(args.extracted)
    by_job, mentions = load_jd()
    total_jobs = len(by_job)
    jd_pairs = {pair for codes in by_job.values() for pair in combinations(sorted(codes), 2)}

    as_of_month = date.today().strftime("%Y-%m")
    with SessionLocal() as db:
        names = {
            code: name
            for code, name in db.execute(
                select(TechnologyNode.technology_code, TechnologyNode.technology_name).where(
                    TechnologyNode.level_code == "L3"
                )
            )
        }

    rejected: Counter[str] = Counter()
    results = []
    for pair, days in up_dates.items():
        count = len(days)
        if count < args.min_cooccurrence:
            continue
        left, right = pair
        if pair in jd_pairs:
            continue

        # 三、语料域偏离：市场上根本不招的方向，其研究侧共现与本项目无关。
        if mentions[left] < args.min_jd_mentions or mentions[right] < args.min_jd_mentions:
            rejected["JD 中提及过少（语料域偏离）"] += 1
            continue
        # 二、同族近义对：同一 L2 内的两个技术是同一件事的两种说法。
        if left.rsplit(".", 1)[0] == right.rsplit(".", 1)[0]:
            rejected["同一 L2（同族近义对）"] += 1
            continue
        # 一、JD 侧漏检：独立性下期望共现不足时，「未共现」不具信息量。
        expected = mentions[left] * mentions[right] / total_jobs if total_jobs else 0
        if expected < args.min_expected_jd:
            rejected["独立性下期望共现过低（缺口无信息量）"] += 1
            continue

        # 锚点 = 共现累积到门槛的那一次，即组合在研究侧站住脚的时间。
        anchor = days[args.min_cooccurrence - 1][:7]
        lag = estimate_transmission_lag((left.split(".")[0], right.split(".")[0]))
        window = None
        if lag.get("status") == "reference_prior":
            window = {
                "from": shift_month(anchor, round(lag["low_months"])),
                "to": shift_month(anchor, round(lag["high_months"])),
                "prior_months": [lag["low_months"], lag["high_months"]],
                "technology_classes": lag["technology_classes"],
            }
        overdue = window is not None and window["to"] < as_of_month
        results.append({
            "overdue": overdue,
            "pair": [left, right],
            "names": [names.get(left, left), names.get(right, right)],
            "upstream_cooccurrence": count,
            "first_upstream_month": days[0][:7],
            "established_month": anchor,
            "jd_mentions": [mentions[left], mentions[right]],
            "expected_jd_cooccurrence": round(expected, 2),
            "reference_window": window,
        })
    results.sort(key=lambda item: (-item["upstream_cooccurrence"], item["first_upstream_month"]))

    payload = {
        "tool_version": TOOL_VERSION,
        "filters": {
            "min_cooccurrence": args.min_cooccurrence,
            "min_expected_jd": args.min_expected_jd,
            "min_jd_mentions": args.min_jd_mentions,
        },
        "rejected": dict(rejected),
        "kept": len(results),
        "items": results,
    }
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=1))
        return

    print(f"# 研究侧已成形、招聘侧未出现的技术组合（{TOOL_VERSION}）\n")
    print(f"- 上游共现门槛 ≥{args.min_cooccurrence} 次 · JD 期望共现下限 "
          f"{args.min_expected_jd} · 单技术 JD 提及下限 {args.min_jd_mentions}\n")
    print("## 噪声过滤\n")
    print("| 剔除原因 | 对数 |")
    print("| --- | ---: |")
    for reason, n in rejected.most_common():
        print(f"| {reason} | {n} |")
    print(f"\n**保留 {len(results)} 对。**\n")
    if not results:
        return
    print("## 保留的组合\n")
    print("| 技术组合 | 上游共现 | 站住脚于 | JD 各自提及 | 期望共现 | 参考区间 |")
    print("| --- | ---: | :---: | ---: | ---: | :---: |")
    for item in results:
        w = item["reference_window"]
        window = f"{w['from']} 至 {w['to']}" if w else "—"
        if item["overdue"]:
            window += " ⚠已过期"
        print(
            f"| {item['names'][0]} + {item['names'][1]} | {item['upstream_cooccurrence']} "
            f"| {item['established_month']} | {item['jd_mentions'][0]}/{item['jd_mentions'][1]} "
            f"| {item['expected_jd_cooccurrence']} | {window} |"
        )
    overdue = sum(1 for item in results if item["overdue"])
    if overdue:
        print(
            f"\n> **{overdue} 对的参考区间已过期**——先验预测它们此时应已进入招聘，"
            "而实际没有。这是该组合**对先验的反证**，不是预测：要么这批技术组合"
            "并不形成岗位，要么本项目的 JD 语料覆盖不到它们，要么分类型时滞先验"
            "在这些组合上不适用。三种解释本系统都无法区分。"
        )
    print(
        "\n> **参考区间不是预测。** 锚点是两个技术首次在上游共现的真实日期；区间由"
        "外部文献的分类型传导时滞先验推出，非本系统测量。本项目 JD 侧时间跨度仅约"
        "10 周且为采集时间，无法验证该区间；U-3 回测进一步表明本项目数据**不支持**"
        "「上游领先招聘」这一前提，因此上表不构成任何岗位将于某时出现的断言。"
    )


if __name__ == "__main__":
    main()
