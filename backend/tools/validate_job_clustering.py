import argparse
import json
from pathlib import Path

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.modules.clustering.models import (
    JobClusteringRun,
    JobClusterMember,
    JobClusterRole,
    JobClusterVersion,
    JobEvolutionChange,
    JobRole,
    JobRoleEvidence,
    JobRoleVersion,
    JobRoleVersionRequirement,
)
from app.modules.data_center.models import ReviewTask
from app.modules.job.models import JobClusterFeatureSnapshot, TechnologyMatchAssessment


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the latest real job clustering run.")
    parser.add_argument("--run-code")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with SessionLocal() as session:
        statement = select(JobClusteringRun).where(JobClusteringRun.run_status_code == "success")
        if args.run_code:
            statement = statement.where(JobClusteringRun.run_code == args.run_code)
        run = session.scalar(statement.order_by(JobClusteringRun.clustering_run_id.desc()))
        if run is None:
            raise SystemExit("No successful clustering run found")
        cluster_ids = list(
            session.scalars(
                select(JobClusterVersion.job_cluster_version_id).where(
                    JobClusterVersion.clustering_run_id == run.clustering_run_id
                )
            )
        )
        members = list(
            session.scalars(
                select(JobClusterMember).where(
                    JobClusterMember.job_cluster_version_id.in_(cluster_ids)
                )
            )
        )
        eligible_count = (
            session.scalar(
                select(func.count())
                .select_from(JobClusterFeatureSnapshot)
                .where(
                    JobClusterFeatureSnapshot.job_parse_run_id == run.job_parse_run_id,
                    JobClusterFeatureSnapshot.eligible_for_clustering.is_(True),
                )
            )
            or 0
        )
        distinct_member_count = len({item.job_posting_id for item in members})
        selected_candidate_count = sum(
            any(candidate.get("selected") is True for candidate in item.top_candidates_json)
            for item in members
        )
        role_ids = list(
            session.scalars(
                select(JobClusterRole.job_role_id).where(
                    JobClusterRole.job_cluster_version_id.in_(cluster_ids)
                )
            )
        )
        role_version_ids = list(
            session.scalars(
                select(JobRoleVersion.job_role_version_id).where(
                    JobRoleVersion.job_role_id.in_(role_ids)
                )
            )
        )
        role_evidence_span_ids = set(
            session.scalars(
                select(JobRoleEvidence.evidence_span_id).where(
                    JobRoleEvidence.job_role_version_id.in_(role_version_ids)
                )
            )
        )
        accepted_evidence_span_ids = set(
            session.scalars(
                select(TechnologyMatchAssessment.evidence_span_id).where(
                    TechnologyMatchAssessment.job_parse_run_id == run.job_parse_run_id,
                    TechnologyMatchAssessment.assessment_status_code == "accepted",
                )
            )
        )
        report = {
            "report_type": "real_job_clustering_validation",
            "run_code": run.run_code,
            "algorithm": {
                "name": run.algorithm_name,
                "version": run.algorithm_version,
                "parameters": run.parameter_json,
                "input_snapshot_hash": run.input_snapshot_hash,
            },
            "input": {
                "eligible_job_count": eligible_count,
                "clustered_member_count": len(members),
                "distinct_clustered_job_count": distinct_member_count,
            },
            "output": {
                "cluster_count": len(cluster_ids),
                "active_cluster_count": session.scalar(
                    select(func.count())
                    .select_from(JobClusterVersion)
                    .where(
                        JobClusterVersion.clustering_run_id == run.clustering_run_id,
                        JobClusterVersion.cluster_status_code == "active",
                    )
                )
                or 0,
                "singleton_cluster_count": session.scalar(
                    select(func.count())
                    .select_from(JobClusterVersion)
                    .where(
                        JobClusterVersion.clustering_run_id == run.clustering_run_id,
                        JobClusterVersion.member_count == 1,
                    )
                )
                or 0,
                "grey_job_count": run.grey_job_count,
                "candidate_role_count": len(set(role_ids)),
                "active_role_count": session.scalar(
                    select(func.count())
                    .select_from(JobRole)
                    .where(
                        JobRole.job_role_id.in_(role_ids),
                        JobRole.lifecycle_status_code == "active",
                    )
                )
                or 0,
                "role_requirement_count": session.scalar(
                    select(func.count())
                    .select_from(JobRoleVersionRequirement)
                    .where(JobRoleVersionRequirement.job_role_version_id.in_(role_version_ids))
                )
                or 0,
                "role_evidence_count": session.scalar(
                    select(func.count())
                    .select_from(JobRoleEvidence)
                    .where(JobRoleEvidence.job_role_version_id.in_(role_version_ids))
                )
                or 0,
            },
            "quality_metrics": run.quality_metric_json,
            "invariants": {
                "every_eligible_job_clustered_once": (
                    eligible_count == len(members) == distinct_member_count
                ),
                "every_member_has_selected_top_candidate": (
                    selected_candidate_count == len(members)
                ),
                "all_role_versions_pending_review": (
                    session.scalar(
                        select(func.count())
                        .select_from(JobRoleVersion)
                        .where(
                            JobRoleVersion.job_role_version_id.in_(role_version_ids),
                            JobRoleVersion.approval_status_code != "pending",
                        )
                    )
                    or 0
                )
                == 0,
                "every_role_version_has_review_task": (
                    session.scalar(
                        select(func.count())
                        .select_from(ReviewTask)
                        .where(
                            ReviewTask.target_type_code == "job_role_version",
                            ReviewTask.target_id.in_(role_version_ids),
                        )
                    )
                    or 0
                )
                == len(role_version_ids),
                "role_evidence_passed_context_validation": role_evidence_span_ids.issubset(
                    accepted_evidence_span_ids
                ),
                "trend_never_claimed_without_history": (
                    session.scalar(
                        select(func.count())
                        .select_from(JobRoleVersionRequirement)
                        .where(
                            JobRoleVersionRequirement.job_role_version_id.in_(role_version_ids),
                            JobRoleVersionRequirement.trend_status_code != "insufficient_history",
                        )
                    )
                    or 0
                )
                == 0,
                "no_removal_proposed_without_history": (
                    session.scalar(
                        select(func.count())
                        .select_from(JobEvolutionChange)
                        .where(JobEvolutionChange.change_type_code == "removed")
                    )
                    or 0
                )
                == 0,
            },
            "truth_boundary": {
                "cluster_is_algorithm_output_not_formal_role": True,
                "candidate_roles_require_human_review": True,
                "source_time_span_insufficient_for_trend": True,
                "scenario_feature_available": False,
                "singleton_clusters_are_not_promoted_to_roles": True,
            },
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
