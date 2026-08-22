"""C-2：标定「技术成熟 → 岗位需求」的传导时滞。

**为什么这件事看起来不可能，但其实有一部分可做。** 直接测时滞需要 JD 的时间
序列——看某技术方向的招聘量在成熟度跨过门槛后多久起量。本项目的 JD 是**单次
快照**（观测窗 2/3 为合成日期），没有真实时间序列，这条路走不通。

但**截尾观测**能给出一个双侧夹逼，且只需要快照：

对每个已跨过门槛的技术方向，记 e = 从跨越时点 t* 到今天的已历时长。

- 该方向**今天已有岗位需求** ⟹ 传导已经完成 ⟹ lag ≤ e
- 该方向**今天尚无岗位需求** ⟹ 传导尚未完成 ⟹ lag > e

若时滞近似是个常数 L，这两组的 e 必须可分：已到达组的 e 全在 L 之上，未到达组
的 e 全在 L 之下。取使误分最少的 L 即为估计值，而**两组的可分程度就是「常数
时滞」这一模型是否成立的检验**。不可分就说明时滞不是常数（或跨越时点算得不准，
或需求根本不由成熟度驱动），此时不应给出窗口。

**必须同时排除的混淆。** 里程碑是人工整理的，整理者可能优先收录了本就热门的
技术方向。若如此，「已到达」与「里程碑多」高度重合，可分性来自整理偏好而非
传导规律。本工具因此同时报告用**里程碑条数**单独做分类的可分性作为对照——
若两者相当，则时滞信号没有超出整理密度所能解释的范围。

用法（backend 目录 / 容器内）：
    python -m tools.experiment_lag_calibration --discovery-run-code discover_xxx
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.db.session import SessionLocal
from app.modules.clustering.models import JobClusteringRun
from app.modules.discovery.foresight import (
    JOBIFICATION_THRESHOLD,
    compute_foresight,
    horizon_label,
    rank_foresight,
)
from app.modules.discovery.models import DiscoveryRun
from app.modules.discovery.service import l2_dated_events
from app.modules.job.models import JobRequirement, TechnologyMatchAssessment
from app.modules.taxonomy.models import TechnologyNode

EXPERIMENT_VERSION = "lag_calibration_v1"
# 「已有岗位需求」的判定，与 budding 门控的「支撑 JD ≥ 3」同口径。
DEFAULT_ARRIVED_JD_COUNT = 3
# 候选的时滞取值（月）。上界 60 个月已远超语料跨度，再大没有判别意义。
LAG_GRID = range(0, 61, 3)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="标定技术成熟到岗位需求的传导时滞。")
    parser.add_argument("--discovery-run-code", required=True)
    parser.add_argument("--arrived-jd-count", type=int, default=DEFAULT_ARRIVED_JD_COUNT)
    parser.add_argument("--threshold", type=float, default=JOBIFICATION_THRESHOLD)
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument(
        "--theta-sweep",
        default="",
        help="逗号分隔的 θ 取值，给出时改为跑敏感性扫描（如 0.25,0.30,0.35,0.40,0.45）",
    )
    return parser.parse_args()


def load_l2_jd_counts(db: Session, parse_run_id: int) -> dict[str, int]:
    """每个 L2 方向被多少份 JD 提及（经其下 L3 的 accepted 证据汇总）。"""
    node = aliased(TechnologyNode)
    parent = aliased(TechnologyNode)
    rows = db.execute(
        select(parent.technology_code, JobRequirement.job_posting_id)
        .join(node, node.technology_node_id == JobRequirement.technology_node_id)
        .join(parent, parent.technology_node_id == node.parent_technology_node_id)
        .join(
            TechnologyMatchAssessment,
            TechnologyMatchAssessment.job_requirement_id == JobRequirement.job_requirement_id,
        )
        .where(
            TechnologyMatchAssessment.job_parse_run_id == parse_run_id,
            TechnologyMatchAssessment.assessment_status_code == "accepted",
        )
        .distinct()
    ).all()
    counts: dict[str, int] = defaultdict(int)
    for code, _job_id in rows:
        if code and code.count(".") == 1:
            counts[code] += 1
    return dict(counts)


def best_split(observations: list[tuple[float, bool]]) -> dict:
    """在候选时滞上扫一遍，取误分最少的那个。

    observations 为 (已历月数, 是否已到达)。常数时滞 L 的预测是
    「已历 ≥ L ⟹ 已到达」，误分即预测与事实不符的方向数。
    """
    total = len(observations)
    best: dict = {"lag_months": None, "errors": total, "accuracy": 0.0}
    for lag in LAG_GRID:
        errors = sum(1 for elapsed, arrived in observations if (elapsed >= lag) != arrived)
        if errors < best["errors"]:
            best = {
                "lag_months": lag,
                "errors": errors,
                "accuracy": round(1 - errors / total, 4) if total else 0.0,
            }
    return best


def best_split_by_count(observations: list[tuple[int, bool]]) -> dict:
    """对照组：改用里程碑条数做同样的一维分类，看可分性是否来自整理密度。"""
    total = len(observations)
    best: dict = {"threshold": None, "errors": total, "accuracy": 0.0}
    for cut in range(0, 60):
        errors = sum(1 for count, arrived in observations if (count >= cut) != arrived)
        if errors < best["errors"]:
            best = {
                "threshold": cut,
                "errors": errors,
                "accuracy": round(1 - errors / total, 4) if total else 0.0,
            }
    return best


def analyse(db: Session, args: argparse.Namespace) -> dict:
    run = db.scalar(select(DiscoveryRun).where(DiscoveryRun.run_code == args.discovery_run_code))
    if run is None:
        raise SystemExit(f"推演运行不存在：{args.discovery_run_code}")
    clustering = db.get(JobClusteringRun, run.clustering_run_id)
    if clustering is None:
        raise SystemExit("推演运行缺少对应的聚类运行")

    # 与线上推演共用同一份归集实现，避免实验口径与线上口径悄悄分叉。
    events_by_l2 = l2_dated_events(db)
    jd_counts = load_l2_jd_counts(db, clustering.job_parse_run_id)
    names = {
        code: name
        for code, name in db.execute(
            select(TechnologyNode.technology_code, TechnologyNode.technology_name).where(
                TechnologyNode.taxonomy_version_id == run.taxonomy_version_id,
                TechnologyNode.level_code == "L2",
            )
        )
    }
    as_of = run.target_date

    results = [
        compute_foresight(
            technology_code=code,
            technology_name=names.get(code, code),
            events=events,
            as_of=as_of,
            threshold=args.threshold,
        )
        for code, events in sorted(events_by_l2.items())
    ]

    directions = []
    for result in results:
        jd_count = jd_counts.get(result.technology_code, 0)
        elapsed = (as_of - result.crossing_date).days / 30.44 if result.crossing_date else None
        directions.append({
            "technology_code": result.technology_code,
            "technology_name": result.technology_name,
            "event_count": result.event_count,
            "peak_maturity": round(result.peak_maturity, 3),
            "maturity_now": round(result.maturity_now, 3),
            "crossing_date": result.crossing_date.isoformat() if result.crossing_date else None,
            "elapsed_months": round(elapsed, 1) if elapsed is not None else None,
            "jd_count": jd_count,
            "arrived": jd_count >= args.arrived_jd_count,
        })

    crossed = [item for item in directions if item["crossing_date"] is not None]
    observations = [(item["elapsed_months"], item["arrived"]) for item in crossed]
    by_count = [(item["event_count"], item["arrived"]) for item in crossed]
    arrived_elapsed = sorted(e for e, a in observations if a)
    pending_elapsed = sorted(e for e, a in observations if not a)

    return {
        "run_code": args.discovery_run_code,
        "as_of": as_of.isoformat(),
        "threshold": args.threshold,
        "l2_with_evidence": len(directions),
        "l2_crossed": len(crossed),
        "arrived_count": len(arrived_elapsed),
        "pending_count": len(pending_elapsed),
        "arrived_elapsed_range": (
            [arrived_elapsed[0], arrived_elapsed[-1]] if arrived_elapsed else None
        ),
        "pending_elapsed_range": (
            [pending_elapsed[0], pending_elapsed[-1]] if pending_elapsed else None
        ),
        "lag_estimate": best_split(observations),
        "milestone_count_control": best_split_by_count(by_count),
        "directions": directions,
        "ranked": [
            {
                "technology_name": item.technology_name,
                "label": horizon_label(item, as_of),
                "peak_maturity": round(item.peak_maturity, 3),
            }
            for item in rank_foresight(results)
        ],
    }


def render(result: dict) -> None:
    print(f"# 传导时滞标定（{EXPERIMENT_VERSION}）\n")
    print(f"- 推演运行：`{result['run_code']}` · 目标日期 {result['as_of']}")
    print(f"- 岗位化门槛 θ = {result['threshold']}（设定值）")
    print(f"- 有里程碑证据的 L2 方向：{result['l2_with_evidence']} 个，"
          f"其中已跨过门槛 {result['l2_crossed']} 个\n")

    print("## 截尾观测的两组\n")
    print("| 组 | 方向数 | 跨越至今已历月数（区间） | 约束 |")
    print("| --- | ---: | --- | --- |")
    arrived = result["arrived_elapsed_range"]
    pending = result["pending_elapsed_range"]
    print(f"| 已有岗位需求 | {result['arrived_count']} "
          f"| {f'{arrived[0]:.1f} – {arrived[1]:.1f}' if arrived else '—'} | lag ≤ 已历 |")
    print(f"| 尚无岗位需求 | {result['pending_count']} "
          f"| {f'{pending[0]:.1f} – {pending[1]:.1f}' if pending else '—'} | lag > 已历 |")

    estimate = result["lag_estimate"]
    control = result["milestone_count_control"]
    print("\n## 常数时滞的可分性\n")
    print("| 判别变量 | 最优切点 | 误分方向数 | 准确率 |")
    print("| --- | ---: | ---: | ---: |")
    print(f"| 跨越至今已历月数 | {estimate['lag_months']} 个月 "
          f"| {estimate['errors']} / {result['l2_crossed']} | {estimate['accuracy']:.1%} |")
    print(f"| 里程碑条数（对照） | {control['threshold']} 条 "
          f"| {control['errors']} / {result['l2_crossed']} | {control['accuracy']:.1%} |")

    if estimate["accuracy"] <= control["accuracy"]:
        print("\n> **时滞的判别力没有超过里程碑条数**——可分性可由整理密度解释，")
        print("> 不足以支持一个常数传导时滞。**不应输出参考窗口**，只保留前瞻排序。")
    elif estimate["accuracy"] < 0.75:
        print("\n> 两组重叠严重，常数时滞模型不成立。**不应输出参考窗口**。")
    else:
        print(f"\n> 两组可分，常数时滞估计为 **{estimate['lag_months']} 个月**，")
        print("> 但这是截尾观测下的点估计，区间宽度需另行确定。")

    print("\n## 已跨过门槛的方向\n")
    print("| 技术方向 | 里程碑 | 峰值成熟度 | 跨越时点 | 已历月数 | JD 数 | 已到达 |")
    print("| --- | ---: | ---: | --- | ---: | ---: | :---: |")
    crossed = [item for item in result["directions"] if item["crossing_date"]]
    for item in sorted(crossed, key=lambda x: x["crossing_date"]):
        print(f"| {item['technology_name']} | {item['event_count']} | {item['peak_maturity']} "
              f"| {item['crossing_date'][:7]} | {item['elapsed_months']} | {item['jd_count']} "
              f"| {'✓' if item['arrived'] else '✗'} |")

    print("\n## 全局前瞻排序（跨域）\n")
    print("| # | 技术方向 | 前瞻判断 |")
    print("| ---: | --- | --- |")
    for index, item in enumerate(result["ranked"], start=1):
        print(f"| {index} | {item['technology_name']} | {item['label']} |")
    print("\n> 跨域排序的已知偏差：成熟度受里程碑整理密度支配，"
          "整理投入多的技术域会系统性排在前面。")


def spearman(first: list[str], second: list[str]) -> float:
    """两个排序在其交集上的秩相关。用于回答「θ 变了排序还站得住吗」。"""
    shared = [code for code in first if code in set(second)]
    if len(shared) < 3:
        return float("nan")
    rank_a = {code: index for index, code in enumerate(first)}
    rank_b = {code: index for index, code in enumerate(second)}
    order_a = sorted(shared, key=lambda code: rank_a[code])
    order_b = sorted(shared, key=lambda code: rank_b[code])
    position_a = {code: index for index, code in enumerate(order_a)}
    position_b = {code: index for index, code in enumerate(order_b)}
    n = len(shared)
    diff = sum((position_a[code] - position_b[code]) ** 2 for code in shared)
    return 1 - (6 * diff) / (n * (n * n - 1))


def sweep(db: Session, args: argparse.Namespace, thetas: list[float]) -> None:
    """θ 敏感性扫描。

    θ 是设定值，因此**排序对它的稳健性决定了这套前瞻判断能不能用**：
    若 θ 动 0.05 名次就大改，那名次反映的是阈值的选择而不是技术的态势。
    """
    runs = []
    for theta in thetas:
        args.threshold = theta
        result = analyse(db, args)
        crossed = [item for item in result["directions"] if item["crossing_date"]]
        crossed.sort(key=lambda item: item["crossing_date"])
        runs.append((theta, result, [item["technology_code"] for item in crossed]))

    print(f"# θ 敏感性扫描（{EXPERIMENT_VERSION}）\n")
    print(f"- 推演运行：`{args.discovery_run_code}` · 目标日期 {runs[0][1]['as_of']}\n")
    print("| θ | 跨过门槛 | 已到达 | 未到达 | 与相邻 θ 的排序秩相关 |")
    print("| ---: | ---: | ---: | ---: | ---: |")
    for index, (theta, result, order) in enumerate(runs):
        correlation = (
            f"{spearman(order, runs[index - 1][2]):.3f}" if index else "—"
        )
        print(f"| {theta} | {result['l2_crossed']} / {result['l2_with_evidence']} "
              f"| {result['arrived_count']} | {result['pending_count']} | {correlation} |")

    print("\n## 各 θ 下的跨越时点（月）\n")
    codes = sorted({code for _theta, _result, order in runs for code in order})
    names = {
        item["technology_code"]: item["technology_name"]
        for _theta, result, _order in runs
        for item in result["directions"]
    }
    print("| 技术方向 | " + " | ".join(f"θ={theta}" for theta, _r, _o in runs) + " | 极差(月) |")
    print("| --- | " + " | ".join("---" for _ in runs) + " | ---: |")
    for code in codes:
        cells, months = [], []
        for _theta, result, _order in runs:
            item = next(x for x in result["directions"] if x["technology_code"] == code)
            if item["crossing_date"]:
                cells.append(item["crossing_date"][:7])
                months.append(item["elapsed_months"])
            else:
                cells.append("—")
        span = f"{max(months) - min(months):.0f}" if len(months) > 1 else "—"
        print(f"| {names[code]} | " + " | ".join(cells) + f" | {span} |")
    print("\n> 极差是同一方向在不同 θ 下跨越时点的最大差距，"
          "反映该方向的跨越时点有多依赖阈值的选取。")


def main() -> None:
    args = parse_args()
    if args.theta_sweep:
        thetas = [float(value) for value in args.theta_sweep.split(",")]
        with SessionLocal() as session:
            sweep(session, args, thetas)
        return
    with SessionLocal() as session:
        result = analyse(session, args)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False))
        return
    render(result)


if __name__ == "__main__":
    main()
