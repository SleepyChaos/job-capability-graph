"""U-3：上游共现对招聘需求的领先性回测。

**要检验的假设。** 岗位 = 雇主把一组能力打包成一个招聘需求。研发、论文发生在
招聘之前，所以若两个技术在上游语料里反复一起出现，它们进入同一个岗位的可能性
应当高于随机——上游共现是招聘需求的领先指标。

**关键设计：只切上游的时间轴，JD 当快照。** 采集时间 ≠ 发布时间 ≠ 岗位出现时间，
三者层层脱节，JD 侧的时间不能当真值。但回测不需要它：

    for T in 年份序列:
        P(T)   = 上游语料中【T 之前】共现 ≥ k 次的技术对
        P(now) = 今天 JD 快照里共现的技术对（不问采集时间）
        命中率 = |P(T) ∩ P(now)| / |P(T)|
        基准率 = |P(now)| / 所有可能的技术对
        提升度 = 命中率 / 基准率

唯一的时间轴在上游，而论文发表日是文档自带属性、不是采集产物，这条轴干净。
T 往前推得越远，测的领先期越长——命中率与领先期同时得到，一个 JD 时间戳都不需要。

**预注册判据（《16》任务书写死，不因结果调整）：**

| 结果 | 结论 |
| --- | --- |
| 提升度 ≤ 1.5 | **证伪，停止**。上游共现不预测招聘需求 |
| 提升度 > 2 且随 T 前移单调下降 | 有领先信号，下降曲线的形状即领先期 |
| 提升度 > 2 但不随 T 变化 | 可能只是「热门技术恒热门」，看对照臂 |

**必须带的对照臂。** 按单技术频次排序挑对——不看共现，只看两个技术各自在上游
出现得多不多。若本方法的提升度与它相当，说明信号可被「热门技术更容易凑到一起」
解释，不构成共现的证据。上一轮传导时滞标定正是栽在没有对照上：最优切点的判别力
与「里程碑条数」完全相同（均 91.7%），那点可分性整理密度就能解释。

用法（backend 目录 / 容器内）：
    python -m tools.experiment_upstream_lead --extracted /srv/data/upstream/extracted
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.db.session import SessionLocal
from app.modules.clustering.models import JobClusteringRun
from app.modules.job.models import JobRequirement, TechnologyMatchAssessment
from app.modules.taxonomy.models import TechnologyNode

EXPERIMENT_VERSION = "upstream_lead_v1"
# 预注册判据，不因结果调整。
FALSIFY_LIFT = 1.5
SUPPORT_LIFT = 2.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="上游共现的领先性回测。")
    parser.add_argument("--extracted", type=Path, required=True)
    parser.add_argument(
        "--min-cooccurrence",
        type=int,
        default=3,
        help="上游共现多少次才算一个「对」。过低会收进偶然同现",
    )
    parser.add_argument(
        "--level",
        choices=["L2", "L3"],
        default="L2",
        help="共现分析的粒度。L3 稀疏，L2 是里程碑与岗位画像共用的层级",
    )
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    return parser.parse_args()


def roll_up(code: str, level: str) -> str | None:
    parts = code.split(".")
    if level == "L2":
        return ".".join(parts[:2]) if len(parts) >= 2 else None
    return code


def load_upstream(directory: Path, level: str) -> dict[int, list[list[str]]]:
    """按年读取上游文档的技术集合。"""
    by_year: dict[int, list[list[str]]] = defaultdict(list)
    for shard in sorted(directory.glob("tech_*.jsonl")):
        for line in shard.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            codes = sorted({
                rolled
                for rolled in (roll_up(code, level) for code in row["technology_codes"])
                if rolled
            })
            if len(codes) >= 2:
                by_year[int(row["published"][:4])].append(codes)
    return by_year


def load_jd_pairs(level: str) -> tuple[set[tuple[str, str]], set[str]]:
    """今天 JD 快照里的技术对，以及出现过的技术集合。不问采集时间。"""
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
    universe: set[str] = set()
    for job_id, code in rows:
        rolled = roll_up(code, level)
        if rolled:
            by_job[job_id].add(rolled)
            universe.add(rolled)
    pairs = set()
    for codes in by_job.values():
        for pair in combinations(sorted(codes), 2):
            pairs.add(pair)
    return pairs, universe


def pairs_before(
    upstream: dict[int, list[list[str]]], cutoff: int, min_count: int
) -> tuple[set[tuple[str, str]], Counter[str]]:
    """T 之前的上游共现对，以及单技术出现频次（供对照臂使用）。"""
    counter: Counter[tuple[str, str]] = Counter()
    singles: Counter[str] = Counter()
    for year, documents in upstream.items():
        if year >= cutoff:
            continue
        for codes in documents:
            singles.update(codes)
            for pair in combinations(codes, 2):
                counter[pair] += 1
    return {pair for pair, count in counter.items() if count >= min_count}, singles


def main() -> None:
    args = parse_args()
    upstream = load_upstream(args.extracted, args.level)
    if not upstream:
        raise SystemExit("上游语料为空，先跑 extract_upstream_technologies")
    jd_pairs, jd_universe = load_jd_pairs(args.level)

    # 基准率的分母是**上游与 JD 共有技术**能组成的全部对——用全体技术会低估基准，
    # 把提升度算虚高。
    upstream_universe = {code for docs in upstream.values() for codes in docs for code in codes}
    shared = upstream_universe & jd_universe
    total_possible = len(shared) * (len(shared) - 1) // 2
    jd_in_scope = {p for p in jd_pairs if p[0] in shared and p[1] in shared}
    base_rate = len(jd_in_scope) / total_possible if total_possible else 0.0

    rows = []
    for cutoff in sorted(upstream)[1:]:
        predicted, singles = pairs_before(upstream, cutoff, args.min_cooccurrence)
        predicted = {p for p in predicted if p[0] in shared and p[1] in shared}
        if not predicted:
            continue
        hit = len(predicted & jd_in_scope)
        hit_rate = hit / len(predicted)

        # 对照臂：不看共现，只按两个技术各自的上游频次挑同样多的对。
        #
        # **必须按频次乘积排序，不能按枚举顺序取。** 首版用 combinations 的顺序截断，
        # 取到的其实是「最高频那几个技术之间的所有对」而非「频次最高的对」，提升度
        # 因此在 2.46 / 0.55 / 1.41 之间乱跳——那不是基线该有的样子，而判据恰恰要
        # 靠对照臂来定。频次乘积正是独立性假设下共现的期望强度，是这里该用的零假设。
        ranked = [code for code, _ in singles.most_common() if code in shared]
        scored = sorted(
            (
                (singles[a] * singles[b], tuple(sorted((a, b))))
                for a, b in combinations(ranked, 2)
            ),
            key=lambda item: -item[0],
        )
        control_pairs = {pair for _score, pair in scored[: len(predicted)]}
        control_hit = len(control_pairs & jd_in_scope) / len(control_pairs) if control_pairs else 0

        rows.append({
            "cutoff_year": cutoff,
            "upstream_documents": sum(len(d) for y, d in upstream.items() if y < cutoff),
            "predicted_pairs": len(predicted),
            "hit": hit,
            "hit_rate": round(hit_rate, 4),
            "lift": round(hit_rate / base_rate, 3) if base_rate else None,
            "control_hit_rate": round(control_hit, 4),
            "control_lift": round(control_hit / base_rate, 3) if base_rate else None,
        })

    result = {
        "experiment_version": EXPERIMENT_VERSION,
        "level": args.level,
        "min_cooccurrence": args.min_cooccurrence,
        "shared_technologies": len(shared),
        "jd_pairs_in_scope": len(jd_in_scope),
        "total_possible_pairs": total_possible,
        "base_rate": round(base_rate, 4),
        "rows": rows,
    }

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return

    print(f"# 上游共现的领先性回测（{EXPERIMENT_VERSION}）\n")
    print(f"- 粒度 {args.level} · 上游共现门槛 ≥{args.min_cooccurrence} 次")
    print(f"- 上游与 JD 共有技术 {len(shared)} 个，可组成 {total_possible} 个对")
    print(f"- JD 快照中实际出现的对 {len(jd_in_scope)} 个 → **基准率 {base_rate:.1%}**\n")
    print("| 切点 T | T 前文档 | 预测对数 | 命中 | 命中率 | 提升度 | 对照臂命中率 | 对照臂提升度 |")
    print("| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in rows:
        print(
            f"| {row['cutoff_year']} | {row['upstream_documents']} | {row['predicted_pairs']} "
            f"| {row['hit']} | {row['hit_rate']:.1%} | **{row['lift']}** "
            f"| {row['control_hit_rate']:.1%} | {row['control_lift']} |"
        )

    if not rows:
        print("\n> 没有可评估的切点。")
        return
    lifts = [row["lift"] or 0 for row in rows]
    controls = [row["control_lift"] or 0 for row in rows]
    best, control_best = max(lifts), max(controls)
    # 预注册判据把「随 T 前移单调下降」与「不随 T 变化」分成两种结论，判定逻辑
    # 必须跟着分——否则一条平坦的曲线会被当成有领先期的曲线报上去。
    # 允许 5% 的抖动：逐点严格单调对 7 个点的样本过于苛刻。
    declining = all(
        lifts[i] >= lifts[i + 1] * 0.95 for i in range(len(lifts) - 1)
    ) and lifts[0] > lifts[-1] * 1.1
    margin = best / control_best if control_best else None

    print("\n## 预注册判据的判定\n")
    if best <= FALSIFY_LIFT:
        print(f"> **证伪**：最高提升度 {best} ≤ {FALSIFY_LIFT}，上游共现不预测招聘需求。")
        print("> 按《16》任务书的预注册判据，此路停止，不进入 U-4。")
    elif best <= control_best:
        print(f"> **信号不成立**：本方法最高提升度 {best}，对照臂 {control_best}，"
              "不优于「按单技术频次挑对」。")
        print("> 说明可被「热门技术更容易凑到一起」解释，不构成共现的证据。")
    elif best <= SUPPORT_LIFT:
        print(f"> **不确定**：最高提升度 {best} 落在 {FALSIFY_LIFT}–{SUPPORT_LIFT} 之间。")
        print("> 需要更大的上游语料或更细的切点才能定论，不宜据此建产品。")
    elif declining:
        print(f"> **支持，且呈现领先期形状**：最高提升度 {best} > {SUPPORT_LIFT}，"
              f"高于对照臂 {control_best}（相对优势 {margin:.2f}×），"
              "且提升度随 T 前移单调下降——下降曲线的形状即领先期。")
    else:
        print(f"> **部分支持，但不构成领先期证据**：最高提升度 {best} > {SUPPORT_LIFT} "
              f"且高于对照臂 {control_best}（相对优势 {margin:.2f}×），"
              "**但提升度不随 T 前移下降**。")
        print("> 按预注册判据，平坦的曲线说明这更像「上游共现与招聘共现同为某种"
              "长期结构的表现」，而不是「上游领先招聘若干年」。可以支持"
              "「上游共现携带 JD 之外的信息」，不能支持「据此预测岗位何时出现」。")


if __name__ == "__main__":
    main()
