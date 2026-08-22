"""C-1：从数据中测「岗位化门槛」θ——技术成熟到什么程度，才会稳定进入招聘需求。

现行 `emerging` 门控里的「技术成熟度 ≥ 0.35」是拍的。本工具用横截面关联把它换成
经验值：对每个 L3 技术点，同时取它的**技术侧成熟度**（由里程碑时间衰减累积得到）
与**岗位侧出现规模**（有多少份 JD 提到它），看成熟度到什么水平时技术开始稳定
出现在招聘需求里。

这是横截面分析，**不需要时间序列**——正是在 JD 侧缺乏跨月真实采集时仍然可做的部分。

⚠️ 必须随结论声明的混淆：里程碑是人工整理的，整理者可能优先收录了本就热门的技术。
若如此，「成熟度高 → JD 出现多」会有一部分是整理偏好造成的循环，而非因果。
本工具用「无里程碑证据的技术点」作对照组来界定这一偏差的规模。

用法（backend 目录 / 容器内）：
    python -m tools.experiment_jobification_threshold --discovery-run-code discover_xxx
"""

from __future__ import annotations

import argparse
import json
import statistics

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.modules.clustering.models import JobClusteringRun
from app.modules.discovery.models import DiscoveryRun, TechnologyMaturitySnapshot
from app.modules.job.models import JobRequirement, TechnologyMatchAssessment
from app.modules.taxonomy.models import TechnologyNode

EXPERIMENT_VERSION = "jobification_threshold_v1"
# 「已岗位化」的判定：技术点出现在至少这么多份 JD 中。
# 取 3 与 budding 门控的「支撑 JD ≥ 3」一致，口径统一。
DEFAULT_JOBIFIED_JD_COUNT = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="测量经验的岗位化门槛 θ。")
    parser.add_argument("--discovery-run-code", required=True)
    parser.add_argument("--jobified-jd-count", type=int, default=DEFAULT_JOBIFIED_JD_COUNT)
    parser.add_argument("--bins", type=int, default=10)
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    return parser.parse_args()


def load_pairs(db: Session, run_code: str, jobified_at: int) -> tuple[list[dict], dict]:
    """取每个 L3 技术点的 (成熟度, 支撑 JD 数)。"""
    run = db.scalar(select(DiscoveryRun).where(DiscoveryRun.run_code == run_code))
    if run is None:
        raise SystemExit(f"推演运行不存在：{run_code}")
    clustering = db.get(JobClusteringRun, run.clustering_run_id)
    if clustering is None:
        raise SystemExit("推演运行缺少对应的聚类运行")

    # 岗位侧：每个技术点被多少份 JD 以 accepted 证据提及
    jd_counts = {
        node_id: count
        for node_id, count in db.execute(
            select(
                JobRequirement.technology_node_id,
                func.count(func.distinct(JobRequirement.job_posting_id)),
            )
            .join(
                TechnologyMatchAssessment,
                TechnologyMatchAssessment.job_requirement_id == JobRequirement.job_requirement_id,
            )
            .where(
                TechnologyMatchAssessment.job_parse_run_id == clustering.job_parse_run_id,
                TechnologyMatchAssessment.assessment_status_code == "accepted",
                JobRequirement.technology_node_id.is_not(None),
            )
            .group_by(JobRequirement.technology_node_id)
        )
    }

    # 技术侧：本次推演的成熟度快照，只取 L3
    rows = db.execute(
        select(
            TechnologyNode.technology_node_id,
            TechnologyNode.technology_code,
            TechnologyNode.technology_name,
            TechnologyMaturitySnapshot.maturity_raw_score,
            TechnologyMaturitySnapshot.verified_event_count,
        )
        .join(
            TechnologyMaturitySnapshot,
            TechnologyMaturitySnapshot.technology_node_id == TechnologyNode.technology_node_id,
        )
        .where(
            TechnologyMaturitySnapshot.discovery_run_id == run.discovery_run_id,
            TechnologyNode.level_code == "L3",
        )
    ).all()

    pairs = [
        {
            "technology_code": code,
            "technology_name": name,
            "maturity": float(maturity),
            "event_count": int(events or 0),
            "jd_count": jd_counts.get(node_id, 0),
            "jobified": jd_counts.get(node_id, 0) >= jobified_at,
        }
        for node_id, code, name, maturity, events in rows
    ]
    return pairs, {"run_code": run_code, "parse_run_id": clustering.job_parse_run_id}


def analyse(pairs: list[dict], bins: int) -> dict:
    with_evidence = [item for item in pairs if item["maturity"] > 0]
    without_evidence = [item for item in pairs if item["maturity"] <= 0]

    def jobified_rate(rows: list[dict]) -> float:
        return sum(1 for item in rows if item["jobified"]) / len(rows) if rows else 0.0

    # 等宽分箱：成熟度 0–1 切 bins 段，看每段的岗位化率
    binned: list[dict] = []
    for index in range(bins):
        low = index / bins
        high = (index + 1) / bins
        rows = [
            item
            for item in with_evidence
            if low <= item["maturity"] < high or (index == bins - 1 and item["maturity"] == 1.0)
        ]
        if not rows:
            continue
        binned.append({
            "low": round(low, 2),
            "high": round(high, 2),
            "count": len(rows),
            "jobified_rate": round(jobified_rate(rows), 4),
            "median_jd_count": statistics.median(item["jd_count"] for item in rows),
        })

    # 拐点：岗位化率相对前一箱提升最大的那个箱的下界
    knee = None
    best_gain = 0.0
    for previous, current in zip(binned, binned[1:], strict=False):
        gain = current["jobified_rate"] - previous["jobified_rate"]
        if gain > best_gain:
            best_gain = gain
            knee = current["low"]

    return {
        "technology_point_count": len(pairs),
        "with_milestone_evidence": len(with_evidence),
        "without_milestone_evidence": len(without_evidence),
        "jobified_rate_with_evidence": round(jobified_rate(with_evidence), 4),
        "jobified_rate_without_evidence": round(jobified_rate(without_evidence), 4),
        "bins": binned,
        "knee_threshold": knee,
        "knee_gain": round(best_gain, 4),
    }


def render(result: dict, pairs: list[dict], args: argparse.Namespace) -> None:
    print(f"# 岗位化门槛 θ 的经验测量（{EXPERIMENT_VERSION}）\n")
    print(f"- 推演运行：`{args.discovery_run_code}`")
    print(f"- 「已岗位化」判定：技术点出现在 ≥ {args.jobified_jd_count} 份 JD 中")
    print(f"- L3 技术点：{result['technology_point_count']} 个"
          f"（有里程碑证据 {result['with_milestone_evidence']}，"
          f"无证据 {result['without_milestone_evidence']}）\n")

    print("## 对照：有无里程碑证据的岗位化率\n")
    print("| 组 | 技术点数 | 已岗位化比例 |")
    print("| --- | ---: | ---: |")
    print(f"| 有里程碑证据 | {result['with_milestone_evidence']} "
          f"| {result['jobified_rate_with_evidence']:.1%} |")
    print(f"| 无里程碑证据 | {result['without_milestone_evidence']} "
          f"| {result['jobified_rate_without_evidence']:.1%} |")

    print("\n## 成熟度分箱 → 岗位化率\n")
    print("| 成熟度区间 | 技术点数 | 已岗位化比例 | JD 数中位 |")
    print("| --- | ---: | ---: | ---: |")
    for row in result["bins"]:
        mark = " ←拐点" if row["low"] == result["knee_threshold"] else ""
        print(f"| {row['low']:.1f}–{row['high']:.1f}{mark} | {row['count']} "
              f"| {row['jobified_rate']:.1%} | {row['median_jd_count']} |")

    if result["knee_threshold"] is not None:
        print(f"\n**拐点位于成熟度 {result['knee_threshold']:.1f}**"
              f"（相对前一箱岗位化率提升 {result['knee_gain']:.1%}）")
    else:
        print("\n**未观察到拐点**——成熟度与岗位化率之间没有明显的阈值效应，"
              "θ 无法由本数据确定，应保留现行取值并声明其为设定值。")

    top = sorted(pairs, key=lambda item: (-item["maturity"], -item["jd_count"]))[:10]
    print("\n## 成熟度最高的 10 个技术点\n")
    print("| 技术点 | 成熟度 | 里程碑数 | JD 数 |")
    print("| --- | ---: | ---: | ---: |")
    for item in top:
        print(f"| {item['technology_name']} | {item['maturity']:.3f} "
              f"| {item['event_count']} | {item['jd_count']} |")


def main() -> None:
    args = parse_args()
    with SessionLocal() as session:
        pairs, meta = load_pairs(session, args.discovery_run_code, args.jobified_jd_count)
    result = analyse(pairs, args.bins)
    if args.format == "json":
        print(json.dumps({**meta, **result}, ensure_ascii=False))
        return
    render(result, pairs, args)


if __name__ == "__main__":
    main()
