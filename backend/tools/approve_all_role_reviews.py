"""Approve all queued job-role review tasks for a reproducible data baseline.

This command deliberately goes through the clustering review service so that
approval metadata, role lifecycle state, evolution-event state, and audit
actions stay consistent. It is idempotent: already approved or otherwise
closed tasks are left unchanged.

Usage::

    APP_DATABASE_URL=... python -m tools.approve_all_role_reviews
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.modules.clustering.service import review_role_version
from app.modules.data_center.models import AppUser, ReviewTask


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewer-code", default="reviewer-demo")
    parser.add_argument(
        "--comment",
        default="数据包导入后的初始岗位聚类全量通过，作为开发环境基线。",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        reviewer = db.scalar(
            select(AppUser).where(
                AppUser.user_code == args.reviewer_code,
                AppUser.is_active.is_(True),
            )
        )
        if reviewer is None or reviewer.role_code not in {"reviewer", "admin"}:
            raise SystemExit(f"审核身份不存在或无权限: {args.reviewer_code}")

        tasks = list(
            db.scalars(
                select(ReviewTask)
                .where(
                    ReviewTask.queue_code == "data_review",
                    ReviewTask.target_type_code == "job_role_version",
                    ReviewTask.task_status_code.in_(
                        ["queued", "assigned", "reviewing", "needs_revision"]
                    ),
                )
                .order_by(ReviewTask.review_task_id)
            )
        )
        for task in tasks:
            review_role_version(
                db,
                task=task,
                actor_user_id=reviewer.user_id,
                action_code="approve",
                comment_text=args.comment,
            )
        db.commit()
        print(f"待审批={len(tasks)}; 已通过={len(tasks)}; 审核人={reviewer.user_code}")


if __name__ == "__main__":
    main()
