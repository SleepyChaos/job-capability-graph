import argparse
import json

from app.db.session import SessionLocal
from app.modules.clustering.algorithm import ClusteringParameters
from app.modules.clustering.service import run_full_clustering


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run deterministic multi-view clustering and propose role versions."
    )
    # 默认值一律从 ClusteringParameters 取，不在这里重述字面量——同一个默认值曾经
    # 分散在算法、CLI、API 三处，改了算法层而漏改入口层导致标定结果实际没生效。
    defaults = ClusteringParameters()
    parser.add_argument("--parse-run-code", required=True)
    parser.add_argument("--assign-threshold", type=float, default=defaults.assign_threshold)
    parser.add_argument("--grey-threshold", type=float, default=defaults.grey_threshold)
    parser.add_argument("--top-k", type=int, default=defaults.top_k)
    parser.add_argument("--max-cluster-size", type=int, default=defaults.max_cluster_size)
    parser.add_argument(
        "--min-technology-evidence-count",
        type=int,
        default=defaults.min_technology_evidence_count,
        help="低信息量过滤门槛（窗口 B 在词表 v1.2 上标定为 1）；0 表示不过滤",
    )
    parser.add_argument(
        "--max-reassign-rounds",
        type=int,
        default=defaults.max_reassign_rounds,
        help="迭代重分配的最大轮次；0 表示关闭迭代，退回单遍贪心",
    )
    args = parser.parse_args()
    if args.grey_threshold >= args.assign_threshold:
        parser.error("--grey-threshold must be lower than --assign-threshold")
    with SessionLocal() as session:
        result = run_full_clustering(
            session,
            parse_run_code=args.parse_run_code,
            parameters=ClusteringParameters(
                assign_threshold=args.assign_threshold,
                grey_threshold=args.grey_threshold,
                top_k=args.top_k,
                max_cluster_size=args.max_cluster_size,
                min_technology_evidence_count=args.min_technology_evidence_count,
                max_reassign_rounds=args.max_reassign_rounds,
            ),
        )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
