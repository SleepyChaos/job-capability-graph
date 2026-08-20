"""抽样稳定性实验：量化「同一语料换个子样本，岗位结构会变多少」。

**为什么这个实验必须先于其它验证。** 岗位动态更新模块报告的每一次 born / ended /
能力变更，都可能有两个来源：岗位真的变了，或者只是抽到的 JD 不同。在不知道后者
有多大之前，前者的任何数字都无法解释。本实验测的就是这个噪声下限——它不证明
方法有效，它给出「多大的变化才算信号」的判据。

三种模式：

- `structure`  不相交对半 → 两半各自独立聚类，按**质心**互相匹配。
                回答「发现的岗位结构是语料的性质，还是这次抽样的性质」。
- `lineage`    重叠子样本 → 复用线上的成员 Jaccard 谱系判定。
                回答「谱系会把多少抽样噪声报成 born / ended」。这是 4.2 的噪声下限。
- `threshold`  扫描谱系阈值 → 在同一对重叠子样本上扫 Jaccard 阈值，
                看 0.55 这个取值处在曲线的什么位置。

口径说明：两个子样本各自独立向量化，因此 IDF 权重不同。这是刻意的——真实的第二次
采集本来就会重算 IDF，共用一套 IDF 反而会高估稳定性。

用法（backend 目录 / 容器内）：
    python -m tools.experiment_sampling_stability --parse-run-code jdparse_xxx --mode structure
    python -m tools.experiment_sampling_stability --parse-run-code jdparse_xxx --mode lineage
    python -m tools.experiment_sampling_stability --parse-run-code jdparse_xxx --mode threshold
"""

from __future__ import annotations

import argparse
import json
import random
import statistics

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.clustering.algorithm import (
    CHANNEL_WEIGHTS,
    ClusterDraft,
    ClusteringParameters,
    cluster_jobs,
    cosine,
    level_similarity,
)
from app.modules.clustering.service import (
    CONTINUED_LINEAGE_JACCARD,
    _continued_matches,
    _evidence_count,
    _raw_feature,
)
from app.modules.job.models import JobClusterFeatureSnapshot, JobParseRun, JobPosting

EXPERIMENT_VERSION = "sampling_stability_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="抽样稳定性实验：测量岗位结构的噪声下限。")
    parser.add_argument("--parse-run-code", required=True)
    parser.add_argument(
        "--mode", choices=["structure", "lineage", "threshold"], default="structure"
    )
    parser.add_argument("--seed", type=int, default=20260820, help="抽样种子，冻结以保证可复现")
    parser.add_argument(
        "--overlap-ratio",
        type=float,
        default=0.8,
        help="lineage/threshold 模式下每个子样本占全量的比例；两样本期望重合度约为该值的平方",
    )
    parser.add_argument("--min-cluster-size", type=int, default=2, help="统计时忽略小于该规模的簇")
    parser.add_argument(
        "--thresholds",
        default="0.30,0.40,0.45,0.50,0.55,0.60,0.65,0.70,0.80",
        help="threshold 模式扫描的谱系 Jaccard 阈值",
    )
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    return parser.parse_args()


def load_rows(session, run_code: str) -> list[tuple]:
    run = session.scalar(
        select(JobParseRun).where(
            JobParseRun.run_code == run_code, JobParseRun.run_status_code == "completed"
        )
    )
    if run is None:
        raise SystemExit(f"已完成的解析运行不存在：{run_code}")
    return session.execute(
        select(JobClusterFeatureSnapshot, JobPosting)
        .join(JobPosting, JobPosting.job_posting_id == JobClusterFeatureSnapshot.job_posting_id)
        .where(
            JobClusterFeatureSnapshot.job_parse_run_id == run.job_parse_run_id,
            JobClusterFeatureSnapshot.eligible_for_clustering.is_(True),
        )
        .order_by(JobClusterFeatureSnapshot.job_posting_id)
    ).all()


def run_clustering(rows: list[tuple], parameters: ClusteringParameters):
    kept = [r for r in rows if _evidence_count(r[0]) >= parameters.min_technology_evidence_count]
    if not kept:
        raise SystemExit("过滤后没有可聚类的 JD")
    return cluster_jobs([_raw_feature(f, j) for f, j in kept], parameters), len(kept)


def cluster_similarity(left: ClusterDraft, right: ClusterDraft) -> float:
    """簇与簇的相似度：与线上 similarity() 同一组通道和权重，只是两侧都取质心。"""
    breakdown = {
        channel: cosine(left.centroid(channel), right.centroid(channel))
        for channel in ("title", "responsibility", "capability", "domain")
    }
    breakdown["level"] = level_similarity(left.dominant_level(), right.dominant_level())
    return sum(CHANNEL_WEIGHTS[channel] * value for channel, value in breakdown.items())


def members_of(cluster: ClusterDraft) -> set[int]:
    return {item.raw.job_posting_id for item in cluster.members}


def split_disjoint(rows: list[tuple], seed: int) -> tuple[list[tuple], list[tuple]]:
    shuffled = list(rows)
    random.Random(seed).shuffle(shuffled)
    middle = len(shuffled) // 2
    return shuffled[:middle], shuffled[middle:]


def sample_overlapping(
    rows: list[tuple], ratio: float, seed: int
) -> tuple[list[tuple], list[tuple]]:
    size = int(len(rows) * ratio)
    first = random.Random(seed).sample(rows, size)
    second = random.Random(seed + 1).sample(rows, size)
    return first, second


def mode_structure(
    rows: list[tuple], args: argparse.Namespace, parameters: ClusteringParameters
) -> dict:
    left_rows, right_rows = split_disjoint(rows, args.seed)
    left, left_n = run_clustering(left_rows, parameters)
    right, right_n = run_clustering(right_rows, parameters)

    left_clusters = [c for c in left.clusters if len(c.members) >= args.min_cluster_size]
    right_clusters = [c for c in right.clusters if len(c.members) >= args.min_cluster_size]
    if not left_clusters or not right_clusters:
        raise SystemExit("任一半没有达到规模下限的簇，无法比较")

    nearest = [max(cluster_similarity(a, b) for b in right_clusters) for a in left_clusters]
    matched = sum(1 for value in nearest if value >= parameters.assign_threshold)
    ordered = sorted(nearest)
    return {
        "mode": "structure",
        "left_job_count": left_n,
        "right_job_count": right_n,
        "left_cluster_count": len(left_clusters),
        "right_cluster_count": len(right_clusters),
        "matched_cluster_count": matched,
        "matched_ratio": round(matched / len(left_clusters), 4),
        "nearest_similarity_mean": round(statistics.fmean(nearest), 4),
        "nearest_similarity_p25": round(ordered[len(ordered) // 4], 4),
        "nearest_similarity_p50": round(ordered[len(ordered) // 2], 4),
        "nearest_similarity_p75": round(ordered[len(ordered) * 3 // 4], 4),
        "assign_threshold": parameters.assign_threshold,
    }


def lineage_counts(previous, current, threshold: float, min_size: int) -> dict:
    """把两次聚类当作前后两代，用线上谱系判定统计 continued / born / ended。"""
    prev_clusters = [c for c in previous.clusters if len(c.members) >= min_size]
    curr_clusters = tuple(c for c in current.clusters if len(c.members) >= min_size)
    previous_members = {c.draft_id: members_of(c) for c in prev_clusters}
    previous_index = dict.fromkeys(previous_members)

    matches = _continued_matches(
        curr_clusters, previous_index, previous_members, threshold=threshold
    )
    continued = len(matches)
    overlaps = [overlap for _old_id, overlap in matches.values()]
    return {
        "threshold": threshold,
        "previous_cluster_count": len(prev_clusters),
        "current_cluster_count": len(curr_clusters),
        "continued": continued,
        "born": len(curr_clusters) - continued,
        "ended": len(prev_clusters) - continued,
        "continued_ratio": round(continued / len(curr_clusters), 4) if curr_clusters else 0.0,
        "mean_matched_overlap": round(statistics.fmean(overlaps), 4) if overlaps else 0.0,
    }


def mode_lineage(
    rows: list[tuple], args: argparse.Namespace, parameters: ClusteringParameters
) -> dict:
    first_rows, second_rows = sample_overlapping(rows, args.overlap_ratio, args.seed)
    shared = len({id(r) for r in first_rows} & {id(r) for r in second_rows})
    first, first_n = run_clustering(first_rows, parameters)
    second, second_n = run_clustering(second_rows, parameters)
    result = lineage_counts(first, second, CONTINUED_LINEAGE_JACCARD, args.min_cluster_size)
    result.update({
        "mode": "lineage",
        "overlap_ratio": args.overlap_ratio,
        "sample_job_count": (first_n, second_n),
        "shared_job_count": shared,
        "shared_ratio": round(shared / len(first_rows), 4) if first_rows else 0.0,
    })
    return result


def mode_threshold(
    rows: list[tuple], args: argparse.Namespace, parameters: ClusteringParameters
) -> dict:
    first_rows, second_rows = sample_overlapping(rows, args.overlap_ratio, args.seed)
    first, _ = run_clustering(first_rows, parameters)
    second, _ = run_clustering(second_rows, parameters)
    thresholds = [float(x) for x in args.thresholds.split(",") if x.strip()]
    return {
        "mode": "threshold",
        "overlap_ratio": args.overlap_ratio,
        "rows": [lineage_counts(first, second, t, args.min_cluster_size) for t in thresholds],
    }


def render(result: dict, args: argparse.Namespace, total: int) -> None:
    print(f"# 抽样稳定性实验（{EXPERIMENT_VERSION}）\n")
    print(f"- 解析运行：`{args.parse_run_code}`")
    print(
        f"- 可聚类特征：{total} 份 · 抽样种子：{args.seed}"
        f" · 簇规模下限：{args.min_cluster_size}\n"
    )

    if result["mode"] == "structure":
        print("## 模式 structure：不相交对半，按质心互相匹配\n")
        print("两半没有任何共同 JD。若发现的岗位结构是语料的性质而非抽样的性质，")
        print("一半里的簇应当能在另一半里找到质心接近的对应簇。\n")
        print("| 项 | 值 |")
        print("| --- | ---: |")
        print(
            f"| 左半 / 右半 参与聚类 JD |"
            f" {result['left_job_count']} / {result['right_job_count']} |"
        )
        print(
            f"| 左半 / 右半 达标簇数 |"
            f" {result['left_cluster_count']} / {result['right_cluster_count']} |"
        )
        print(f"| **有对应簇的比例** | **{result['matched_ratio']:.1%}** |")
        print(f"| 最近质心相似度 均值 | {result['nearest_similarity_mean']} |")
        print(f"| 最近质心相似度 p25 / p50 / p75 | {result['nearest_similarity_p25']} / "
              f"{result['nearest_similarity_p50']} / {result['nearest_similarity_p75']} |")
        print(f"| 判定为「有对应」的阈值 | {result['assign_threshold']}（与线上分配阈值一致） |")
        return

    if result["mode"] == "lineage":
        print("## 模式 lineage：重叠子样本，用线上谱系判定\n")
        print(f"两个子样本各取全量的 {result['overlap_ratio']:.0%}，实际共享 "
              f"{result['shared_job_count']} 份（{result['shared_ratio']:.1%}）。")
        print("语料是同一批，**这里报出的 born / ended 全部是抽样噪声，不是岗位演化**。\n")
        print("| 项 | 值 |")
        print("| --- | ---: |")
        print(
            f"| 前代 / 本代 达标簇数 |"
            f" {result['previous_cluster_count']} / {result['current_cluster_count']} |"
        )
        print(f"| **continued** | **{result['continued']}**（{result['continued_ratio']:.1%}） |")
        print(f"| born（噪声） | {result['born']} |")
        print(f"| ended（噪声） | {result['ended']} |")
        print(f"| 匹配簇的平均成员重合度 | {result['mean_matched_overlap']} |")
        print(f"| 谱系阈值 | {CONTINUED_LINEAGE_JACCARD} |")
        return

    print("## 模式 threshold：谱系阈值敏感性\n")
    print(f"同一对重叠子样本（各取 {result['overlap_ratio']:.0%}）上扫描阈值。\n")
    print("| Jaccard 阈值 | continued | born | ended | 延续率 | 匹配簇平均重合度 |")
    print("| ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in result["rows"]:
        mark = " ←线上" if abs(row["threshold"] - CONTINUED_LINEAGE_JACCARD) < 1e-9 else ""
        print(f"| {row['threshold']:.2f}{mark} | {row['continued']} | {row['born']} | "
              f"{row['ended']} | {row['continued_ratio']:.1%} | {row['mean_matched_overlap']} |")


def main() -> None:
    args = parse_args()
    parameters = ClusteringParameters()
    with SessionLocal() as session:
        rows = load_rows(session, args.parse_run_code)

    handler = {"structure": mode_structure, "lineage": mode_lineage, "threshold": mode_threshold}
    result = handler[args.mode](list(rows), args, parameters)

    if args.format == "json":
        print(json.dumps({"parse_run_code": args.parse_run_code, "seed": args.seed, **result},
                         ensure_ascii=False))
        return
    render(result, args, len(rows))


if __name__ == "__main__":
    main()
