from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.modules.clustering.models import (
    JobEvolutionEvent,
    JobRole,
    JobRoleVersion,
)
from app.modules.clustering.service import review_role_version
from app.modules.data_center.models import AppUser, ReviewAction, ReviewTask


def test_role_version_review_publishes_candidate_and_audit_snapshot() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        reviewer = AppUser(
            user_code="role-reviewer",
            display_name="岗位审核员",
            role_code="reviewer",
        )
        role = JobRole(
            role_code="ROLE-SYNTH",
            canonical_name="合成岗位",
            normalized_name="合成岗位",
            origin_type_code="cluster_derived",
            lifecycle_status_code="candidate",
        )
        session.add_all([reviewer, role])
        session.flush()
        version = JobRoleVersion(
            job_role_id=role.job_role_id,
            version_no=1,
            valid_from=date(2026, 8, 11),
            role_name="合成岗位",
            one_line_definition="仅用于审核状态机测试。",
            core_responsibility_text="合成职责",
            generation_method_code="statistical",
            evidence_strength_score=Decimal("80"),
        )
        session.add(version)
        session.flush()
        event = JobEvolutionEvent(
            event_code="EV-SYNTH",
            job_role_id=role.job_role_id,
            to_role_version_id=version.job_role_version_id,
            event_type_code="created",
            change_summary="合成初始版本",
            confidence_score=Decimal("80"),
        )
        task = ReviewTask(
            task_code="RT-ROLE-SYNTH",
            queue_code="data_review",
            target_type_code="job_role_version",
            target_id=version.job_role_version_id,
            priority_score=Decimal("50"),
            target_snapshot_json={"role_name": "合成岗位"},
        )
        session.add_all([event, task])
        session.flush()

        approved = review_role_version(
            session,
            task=task,
            actor_user_id=reviewer.user_id,
            action_code="approve",
            comment_text="合成审核通过",
        )
        session.commit()

        assert approved.approval_status_code == "approved"
        assert role.lifecycle_status_code == "active"
        assert event.approval_status_code == "approved"
        assert task.task_status_code == "approved"
        assert session.scalar(select(func.count()).select_from(ReviewAction)) == 1
