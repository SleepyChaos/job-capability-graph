"""为缺审核任务的候选补建任务。

上游候选（`build_upstream_candidates`）首版落库时没建 `ReviewTask`，导致这 25 条在
审核台上可见却无法处置——处置接口按 `task_code` 定位。构建工具已修好，此脚本只补
历史数据，按候选逐条判定，已有待办任务的跳过，可重复执行。
"""

from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.data_center.models import ReviewTask
from app.modules.discovery.models import EmergingRoleCandidate
from app.modules.discovery.service import candidate_snapshot


def main() -> None:
    with SessionLocal() as session:
        existing = {
            task.target_id
            for task in session.scalars(
                select(ReviewTask).where(
                    ReviewTask.target_type_code == "emerging_role",
                    ReviewTask.task_status_code.in_(("queued", "pending")),
                )
            )
        }
        candidates = session.scalars(
            select(EmergingRoleCandidate).where(
                EmergingRoleCandidate.workflow_status_code == "pending"
            )
        ).all()
        added = 0
        for candidate in candidates:
            if candidate.emerging_role_candidate_id in existing:
                continue
            session.add(
                ReviewTask(
                    task_code=f"review_discovery_{candidate.candidate_code}",
                    queue_code="job_discovery",
                    target_type_code="emerging_role",
                    target_id=candidate.emerging_role_candidate_id,
                    priority_score=candidate.candidate_score,
                    task_status_code="queued",
                    target_snapshot_json=candidate_snapshot(session, candidate),
                    reason_json={
                        "risk_flags": candidate.risk_flags_json or [],
                        "source": "backfill",
                    },
                )
            )
            added += 1
        session.commit()
        print(f"待审候选 {len(candidates)} 条，补建审核任务 {added} 条")


if __name__ == "__main__":
    main()
