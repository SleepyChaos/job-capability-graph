import argparse
from datetime import date

from app.db.session import SessionLocal
from app.modules.discovery.service import run_discovery


def main() -> None:
    parser = argparse.ArgumentParser(description="运行可回放的新岗位发现")
    parser.add_argument(
        "--mode",
        choices=["automatic", "technology_directed", "name_inference"],
        default="automatic",
    )
    parser.add_argument("--target-date", type=date.fromisoformat, required=True)
    parser.add_argument("--technology-id", type=int, action="append", default=[])
    parser.add_argument("--role-name")
    parser.add_argument("--description")
    args = parser.parse_args()
    with SessionLocal() as session:
        result = run_discovery(
            session,
            mode_code=args.mode,
            target_date=args.target_date,
            selected_technology_ids=args.technology_id,
            query_role_name=args.role_name,
            query_description=args.description,
        )
    print(
        {
            "run_code": result.run_code,
            "candidate_count": result.candidate_count,
            "task_count": result.task_count,
            "evidence_limited": result.evidence_limited,
            "already_completed": result.already_completed,
        }
    )


if __name__ == "__main__":
    main()
