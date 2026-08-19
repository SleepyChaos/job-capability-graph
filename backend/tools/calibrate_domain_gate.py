"""标定聚类入口的低信息量过滤门槛（窗口 B-1）。

在内存里跑聚类算法本身（不落库、不产生聚类运行），对一组门槛值逐一测量结果形态，
把「门槛怎么定」从拍脑袋变成有数据依据。词表升版后每份 JD 的技术证据条数普遍上升，
门槛的含义随之改变，因此每次换词表都必须重跑本工具。

指标口径：
- 参与聚类 / 被过滤：按特征快照 `technology_weights` 条数与门槛比较（与线上同一函数）
- 单例簇 JD 比：只含 1 份 JD 的簇所覆盖的 JD 占参与聚类 JD 的比例——它衡量「碎片化」，
  是低信息量 JD 污染聚类的直接症状
- 一致性：簇内成员到质心的相似度均值×100，与线上 `coherence_score` 同一算法
- 灰区比：落入灰区（相似度介于 grey/assign 阈值之间）的 JD 占比

用法（backend 目录 / 容器内）：
    python -m tools.calibrate_domain_gate --parse-run-code jdparse_xxx
    python -m tools.calibrate_domain_gate --parse-run-code jdparse_xxx --thresholds 0,1,2,3
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.clustering.algorithm import ClusteringParameters, cluster_jobs, similarity
from app.modules.clustering.service import _evidence_count, _raw_feature
from app.modules.job.models import JobClusterFeatureSnapshot, JobParseRun, JobPosting


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="标定聚类入口的低信息量过滤门槛。")
    parser.add_argument("--parse-run-code", required=True)
    parser.add_argument("--thresholds", default="0,1,2,3,4,5")
    defaults = ClusteringParameters()
    parser.add_argument("--assign-threshold", type=float, default=defaults.assign_threshold)
    parser.add_argument("--grey-threshold", type=float, default=defaults.grey_threshold)
    parser.add_argument("--top-k", type=int, default=defaults.top_k)
    parser.add_argument("--max-cluster-size", type=int, default=defaults.max_cluster_size)
    parser.add_argument("--max-reassign-rounds", type=int, default=defaults.max_reassign_rounds)
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    return parser.parse_args()


def measure(rows: list[tuple], threshold: int, args: argparse.Namespace) -> dict:
    kept = [row for row in rows if _evidence_count(row[0]) >= threshold]
    filtered = len(rows) - len(kept)
    if not kept:
        return {"threshold": threshold, "clustered_job_count": 0, "filtered_job_count": filtered}
    parameters = ClusteringParameters(
        assign_threshold=args.assign_threshold,
        grey_threshold=args.grey_threshold,
        top_k=args.top_k,
        max_cluster_size=args.max_cluster_size,
        min_technology_evidence_count=threshold,
        max_reassign_rounds=args.max_reassign_rounds,
    )
    output = cluster_jobs([_raw_feature(feature, job) for feature, job in kept], parameters)
    sizes = sorted(len(cluster.members) for cluster in output.clusters)
    singleton_clusters = sum(1 for size in sizes if size == 1)
    coherences = [
        statistics.fmean(similarity(member, cluster).total for member in cluster.members) * 100
        for cluster in output.clusters
        if cluster.members
    ]
    status = Counter(decision.status_code for decision in output.decisions)
    total = len(kept)
    return {
        "threshold": threshold,
        "clustered_job_count": total,
        "filtered_job_count": filtered,
        "cluster_count": len(output.clusters),
        "singleton_cluster_count": singleton_clusters,
        # 单例簇里每个簇正好 1 份 JD，所以单例簇数就是被碎片化的 JD 数。
        "singleton_job_ratio": round(singleton_clusters / total, 4),
        "size_p50": sizes[len(sizes) // 2] if sizes else 0,
        "size_p90": sizes[int(len(sizes) * 0.9)] if sizes else 0,
        "size_max": sizes[-1] if sizes else 0,
        "mean_coherence": round(statistics.fmean(coherences), 2) if coherences else 0,
        "grey_ratio": round(status.get("grey", 0) / total, 4),
    }


def main() -> None:
    args = parse_args()
    thresholds = [int(item) for item in args.thresholds.split(",") if item.strip()]
    with SessionLocal() as session:
        run = session.scalar(
            select(JobParseRun).where(
                JobParseRun.run_code == args.parse_run_code,
                JobParseRun.run_status_code == "completed",
            )
        )
        if run is None:
            raise SystemExit(f"已完成的解析运行不存在：{args.parse_run_code}")
        rows = session.execute(
            select(JobClusterFeatureSnapshot, JobPosting)
            .join(JobPosting, JobPosting.job_posting_id == JobClusterFeatureSnapshot.job_posting_id)
            .where(
                JobClusterFeatureSnapshot.job_parse_run_id == run.job_parse_run_id,
                JobClusterFeatureSnapshot.eligible_for_clustering.is_(True),
            )
            .order_by(JobClusterFeatureSnapshot.job_posting_id)
        ).all()

    results = [measure(list(rows), threshold, args) for threshold in thresholds]
    if args.format == "json":
        payload = {"parse_run_code": args.parse_run_code, "rows": results}
        print(json.dumps(payload, ensure_ascii=False))
        return
    print(f"解析运行 {args.parse_run_code}，可聚类特征 {len(rows)} 份\n")
    print(
        "| 门槛 | 参与聚类 | 被过滤 | 簇数 | 单例簇 | 单例JD比 "
        "| p50 | p90 | max | 一致性 | 灰区比 |"
    )
    print("| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in results:
        print(
            f"| {row['threshold']} | {row['clustered_job_count']} | {row['filtered_job_count']} "
            f"| {row['cluster_count']} | {row['singleton_cluster_count']} "
            f"| {row['singleton_job_ratio']:.1%} | {row['size_p50']} | {row['size_p90']} "
            f"| {row['size_max']} | {row['mean_coherence']} | {row['grey_ratio']:.1%} |"
        )


if __name__ == "__main__":
    main()
