import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.modules.data_center.models import ReviewTask
from app.modules.discovery.models import (
    CandidateScoreComponent,
    DiscoveryRun,
    EmergingRoleCandidate,
    IndustryTask,
    IndustryTaskEvidence,
    StandardJobDescription,
    TechnologyMaturitySnapshot,
)
from app.modules.job.models import JobPosting


def main() -> None:
    parser = argparse.ArgumentParser(description="验证新岗位发现运行的证据和状态不变量")
    parser.add_argument("--run-code", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with SessionLocal() as session:
        report = build_report(session, args.run_code)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))


def build_report(session, run_code: str) -> dict:
    run = session.scalar(select(DiscoveryRun).where(DiscoveryRun.run_code == run_code))
    if run is None:
        raise SystemExit("发现运行不存在")
    candidates = list(
        session.scalars(
            select(EmergingRoleCandidate).where(
                EmergingRoleCandidate.discovery_run_id == run.discovery_run_id
            )
        )
    )
    tasks = list(
        session.scalars(
            select(IndustryTask).where(IndustryTask.discovery_run_id == run.discovery_run_id)
        )
    )
    candidate_ids = [item.emerging_role_candidate_id for item in candidates]
    task_ids = [item.industry_task_id for item in tasks]
    review_count = (
        session.scalar(
            select(func.count())
            .select_from(ReviewTask)
            .where(
                ReviewTask.queue_code == "job_discovery",
                ReviewTask.target_id.in_(candidate_ids or [-1]),
            )
        )
        or 0
    )
    evidence_rows = session.execute(
        select(IndustryTaskEvidence, JobPosting)
        .join(JobPosting, JobPosting.job_posting_id == IndustryTaskEvidence.job_posting_id)
        .where(IndustryTaskEvidence.industry_task_id.in_(task_ids or [-1]))
    ).all()
    cutoff = datetime.combine(run.target_date, datetime.max.time())
    future_evidence = [
        evidence.evidence_span_id
        for evidence, posting in evidence_rows
        if not (
            (posting.source_collected_at and posting.source_collected_at <= cutoff)
            or (
                posting.source_collected_at is None
                and posting.published_at
                and posting.published_at <= cutoff
            )
        )
    ]
    components_per_candidate = dict(
        session.execute(
            select(
                CandidateScoreComponent.emerging_role_candidate_id,
                func.count(CandidateScoreComponent.candidate_score_component_id),
            )
            .where(CandidateScoreComponent.emerging_role_candidate_id.in_(candidate_ids or [-1]))
            .group_by(CandidateScoreComponent.emerging_role_candidate_id)
        ).all()
    )
    maturity_rows = list(
        session.scalars(
            select(TechnologyMaturitySnapshot).where(
                TechnologyMaturitySnapshot.discovery_run_id == run.discovery_run_id
            )
        )
    )
    standard_jd_market_count = (
        session.scalar(
            select(func.count())
            .select_from(StandardJobDescription)
            .where(
                StandardJobDescription.emerging_role_candidate_id.in_(candidate_ids or [-1]),
                StandardJobDescription.is_market_evidence.is_(True),
            )
        )
        or 0
    )
    risks = Counter(flag for item in candidates for flag in item.risk_flags_json)
    invariants = {
        "all_tasks_have_traceable_evidence": bool(tasks)
        and all(item.evidence_status_code == "traceable" for item in tasks),
        "all_evidence_links_real_jd": len(evidence_rows)
        == session.scalar(
            select(func.count())
            .select_from(IndustryTaskEvidence)
            .where(IndustryTaskEvidence.industry_task_id.in_(task_ids or [-1]))
        ),
        "target_date_has_no_future_jd_evidence": not future_evidence,
        "each_candidate_has_eight_positive_score_dimensions": bool(candidates)
        and all(
            components_per_candidate.get(item.emerging_role_candidate_id, 0) >= 8
            for item in candidates
        ),
        "workflow_and_maturity_are_separate": all(
            item.workflow_status_code != "approved" or item.maturity_stage_code == "confirmed"
            for item in candidates
        ),
        "every_pending_candidate_has_special_review": review_count
        == sum(item.workflow_status_code == "pending" for item in candidates),
        "standard_jd_never_counts_as_market_evidence": standard_jd_market_count == 0,
        "missing_verified_milestones_never_claims_emerging": all(
            item.maturity_stage_code != "emerging" for item in candidates
        )
        if not any(item.verified_event_count for item in maturity_rows)
        else True,
    }
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run": {
            "run_code": run.run_code,
            "mode_code": run.mode_code,
            "target_date": run.target_date.isoformat(),
            "algorithm_version": run.algorithm_version,
            "input_snapshot_hash": run.input_snapshot_hash,
            "input_snapshot": run.input_snapshot_json,
        },
        "summary": {
            "candidate_count": len(candidates),
            "task_count": len(tasks),
            "task_evidence_count": len(evidence_rows),
            "review_task_count": review_count,
            "maturity_snapshot_count": len(maturity_rows),
            "verified_maturity_snapshot_count": sum(
                item.verified_event_count > 0 for item in maturity_rows
            ),
            "stage_counts": dict(Counter(item.maturity_stage_code for item in candidates)),
            "classification_counts": dict(Counter(item.classification_code for item in candidates)),
            "risk_counts": dict(risks.most_common()),
            "score_min": min((float(item.candidate_score) for item in candidates), default=None),
            "score_max": max((float(item.candidate_score) for item in candidates), default=None),
            "invariants": invariants,
        },
        "future_evidence_ids": future_evidence,
    }


if __name__ == "__main__":
    main()
