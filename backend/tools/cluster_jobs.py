import argparse
import json

from app.db.session import SessionLocal
from app.modules.clustering.algorithm import ClusteringParameters
from app.modules.clustering.service import run_full_clustering


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run deterministic multi-view clustering and propose role versions."
    )
    parser.add_argument("--parse-run-code", required=True)
    parser.add_argument("--assign-threshold", type=float, default=0.36)
    parser.add_argument("--grey-threshold", type=float, default=0.24)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--max-cluster-size", type=int, default=120)
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
            ),
        )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
