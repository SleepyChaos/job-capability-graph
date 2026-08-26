"""找出「研究侧已成形、招聘侧未出现」的技术组合，并给出参考出现区间。

**这不是「全新岗位预测」。** 产出的是能力组合，不是岗位；给出的区间来自外部文献
先验，不是本系统的测量。命名与措辞必须守住这条界线——U-3 回测已经明确否掉了
「上游领先招聘若干年」这个命题（提升度不随时点前移下降），任何形如「该岗位将于 X
出现」的说法都没有依据。

**接受不确定性，但不冒充确定性。** 按《17》的验收口径，不要求每条都准，
要求每条都标明置信等级与依据——C 级条目可以出，但不能被描述成「发现的新岗位」。

## 分级而非过滤

**此前的做法是错的。** 早先版本用三道过滤只留「确定的」，结果 88 对被砍到 2 对，
而被砍掉的里面混着两种性质完全不同的东西：

- 语料域偏离（arXiv 的无人机研究与具身智能招聘市场无关）——确实是噪声
- **该技术在招聘市场上还没出现**——而那恰恰是新岗位信号本身

两者被混为一谈，且工具替审阅者做了删除决定。现改为**全部输出并分级**，
把判断权交回去：

- **A**：两侧技术在 JD 中均常见，独立性下期望共现 ≥ 阈值而实测为 0。
  缺口最可信——市场在招这两个方向，却从不合招。
- **B**：两侧技术在 JD 中均出现过，但期望共现不足阈值。
  缺口存在，样本量不足以排除偶然。
- **C**：至少一侧技术在 JD 中从未出现。
  可能是最新的信号，也可能是语料域偏离——本系统无法区分，交审阅者判断。

**只有一类仍然直接剔除**：同一 L2 下的同族近义对（无人机 + 飞行器(通用)）。
它们是词表结构造成的假象，不是能力组合，放进来只会稀释真实信号。

A 级的期望共现判据用的是**独立性下的期望值**：若两个技术各自在 JD 中常见，
独立假设预测它们本应共现若干次而实测为 0，这个「0」才有信息量；若期望本就不足
1 次，没共现说明不了任何事。这与领先性回测里对照臂用的是同一个零假设。

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
        "--expected-jd-threshold",
        type=float,
        default=2.0,
        help="A 级要求的独立性期望共现数下限。低于它降为 B 级，不再直接剔除",
    )
    parser.add_argument(
        "--grades",
        default="A,B,C",
        help="输出哪些等级，逗号分隔。默认全出",
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
    grades = {g.strip().upper() for g in args.grades.split(",") if g.strip()}
    results = []
    for pair, days in up_dates.items():
        count = len(days)
        if count < args.min_cooccurrence:
            continue
        left, right = pair
        if pair in jd_pairs:
            continue

        # 唯一仍然直接剔除的一类：同一 L2 下的同族近义对，是词表结构造成的假象。
        if left.rsplit(".", 1)[0] == right.rsplit(".", 1)[0]:
            rejected["同一 L2（同族近义对）"] += 1
            continue

        expected = mentions[left] * mentions[right] / total_jobs if total_jobs else 0
        if mentions[left] == 0 or mentions[right] == 0:
            grade = "C"
            grade_reason = (
                "至少一侧技术在 JD 中从未出现——可能是最新信号，也可能是语料域偏离"
            )
        elif expected >= args.expected_jd_threshold:
            grade = "A"
            grade_reason = "两侧技术在 JD 中均常见，独立性下本应共现却从未共现"
        else:
            grade = "B"
            grade_reason = "两侧技术在 JD 中均出现过，但样本量不足以排除偶然"
        if grade not in grades:
            rejected[f"等级 {grade} 未被请求输出"] += 1
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
            "grade": grade,
            "grade_reason": grade_reason,
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
    results.sort(
        key=lambda item: (item["grade"], -item["upstream_cooccurrence"], item["established_month"])
    )

    payload = {
        "tool_version": TOOL_VERSION,
        "filters": {
            "min_cooccurrence": args.min_cooccurrence,
            "expected_jd_threshold": args.expected_jd_threshold,
            "grades": sorted(grades),
        },
        "by_grade": dict(Counter(item["grade"] for item in results)),
        "rejected": dict(rejected),
        "kept": len(results),
        "items": results,
    }
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=1))
        return

    print(f"# 研究侧已成形、招聘侧未出现的技术组合（{TOOL_VERSION}）\n")
    print(f"- 上游共现门槛 ≥{args.min_cooccurrence} 次 · A 级期望共现阈值 "
          f"{args.expected_jd_threshold}\n")
    by_grade = Counter(item["grade"] for item in results)
    print("## 分级结果\n")
    print("| 等级 | 对数 | 含义 |")
    print("| :---: | ---: | --- |")
    labels = {
        "A": "两侧技术 JD 中均常见，独立性下本应共现却从未共现——缺口最可信",
        "B": "两侧技术 JD 中均出现过，但样本量不足以排除偶然",
        "C": "至少一侧技术 JD 中从未出现——可能是最新信号，也可能是语料域偏离",
    }
    for grade in ("A", "B", "C"):
        if grade in by_grade:
            print(f"| **{grade}** | {by_grade[grade]} | {labels[grade]} |")
    if rejected:
        print("\n剔除：" + " · ".join(f"{k} {v}" for k, v in rejected.most_common()))
    if not results:
        print("\n> 当前语料条件下无产出。空结果本身是结论，不隐藏该功能。")
        return

    for grade in ("A", "B", "C"):
        rows = [item for item in results if item["grade"] == grade]
        if not rows:
            continue
        print(f"\n## {grade} 级（{len(rows)} 对）\n")
        print("| 技术组合 | 上游共现 | 站住脚于 | JD 各自提及 | 期望共现 | 参考区间 |")
        print("| --- | ---: | :---: | ---: | ---: | :---: |")
        for item in rows[:40]:
            w = item["reference_window"]
            window = f"{w['from']} 至 {w['to']}" if w else "—"
            if item["overdue"]:
                window += " ⚠已过期"
            print(
                f"| {item['names'][0]} + {item['names'][1]} "
                f"| {item['upstream_cooccurrence']} | {item['established_month']} "
                f"| {item['jd_mentions'][0]}/{item['jd_mentions'][1]} "
                f"| {item['expected_jd_cooccurrence']} | {window} |"
            )
        if len(rows) > 40:
            print(f"\n> 另有 {len(rows) - 40} 对未列出，完整清单见 --format json。")

    overdue = sum(1 for item in results if item["overdue"])
    print("\n## 必须随结果一并声明\n")
    if overdue:
        print(
            f"- **{overdue} 对的参考区间已过期**——先验预测它们此时应已进入招聘而实际没有。"
            "这是对先验的反证，不是预测：要么该组合不形成岗位，要么本项目 JD 语料"
            "覆盖不到，要么分类型时滞先验在这些组合上不适用，本系统无法区分三者。"
        )
    print(
        "- **参考区间不是测量。** 锚点是两个技术在上游累积到共现门槛的真实日期；"
        "区间由外部文献的分类型传导时滞先验推出。本项目 JD 侧时间跨度仅约 10 周"
        "且为采集时间，无法验证；U-3 回测进一步表明本项目数据不支持「上游领先招聘」"
        "这一前提本身。"
    )
    print(
        "- **C 级不是「发现的新岗位」**，是待核查的信号。它与「语料域偏离」在本系统内"
        "无法区分，需要人工判断该技术方向是否确实属于具身智能招聘市场。"
    )


if __name__ == "__main__":
    main()
