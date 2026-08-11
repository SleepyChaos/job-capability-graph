import hashlib
import json
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.clustering.algorithm import (
    ClusterDraft,
    ClusteringOutput,
    ClusteringParameters,
    RawJobFeature,
    cluster_jobs,
    decimal_score,
    similarity,
)
from app.modules.clustering.models import (
    JobClusterDomain,
    JobClusteringRun,
    JobClusterLineage,
    JobClusterMember,
    JobClusterRole,
    JobClusterVersion,
    JobEvolutionChange,
    JobEvolutionEvent,
    JobRole,
    JobRoleAlias,
    JobRoleEvidence,
    JobRoleVersion,
    JobRoleVersionRequirement,
)
from app.modules.data_center.models import ReviewAction, ReviewTask
from app.modules.job.models import (
    EvidenceSpan,
    JobClusterFeatureSnapshot,
    JobParseRun,
    JobPosting,
    JobPostingDataSource,
    JobRequirement,
    JobRequirementEvidence,
    JobResponsibility,
    TechnologyMatchAssessment,
)
from app.modules.taxonomy.models import TechnologyDomain, TechnologyNode

ALGORITHM_NAME = "explainable_sparse_multiview"
ALGORITHM_VERSION = "baseline_sparse_multiview_v1"
CALCULATION_VERSION = "role_capability_stats_v1"


class ClusteringError(ValueError):
    """A user-correctable clustering or role-evolution error."""


@dataclass(frozen=True)
class ClusteringRunResult:
    run_code: str
    input_job_count: int
    cluster_count: int
    grey_job_count: int
    candidate_role_count: int
    already_completed: bool


@dataclass(frozen=True)
class CapabilityMetric:
    technology_node_id: int
    technology_code: str
    requirement_type_code: str
    long_term_importance: Decimal
    recent_activity: Decimal
    coverage_rate: Decimal
    required_ratio: Decimal
    trend_score: Decimal | None
    trend_status_code: str
    supporting_job_count: int
    organization_count: int
    source_count: int
    last_seen_at: datetime | None
    confidence_score: Decimal
    evidence_ids: tuple[int, ...]


def run_full_clustering(
    db: Session,
    *,
    parse_run_code: str,
    parameters: ClusteringParameters | None = None,
) -> ClusteringRunResult:
    parameters = parameters or ClusteringParameters()
    parse_run = db.scalar(
        select(JobParseRun).where(
            JobParseRun.run_code == parse_run_code,
            JobParseRun.run_status_code == "completed",
        )
    )
    if parse_run is None:
        raise ClusteringError("已完成的JD解析运行不存在")
    feature_rows = db.execute(
        select(JobClusterFeatureSnapshot, JobPosting)
        .join(
            JobPosting,
            JobPosting.job_posting_id == JobClusterFeatureSnapshot.job_posting_id,
        )
        .where(
            JobClusterFeatureSnapshot.job_parse_run_id == parse_run.job_parse_run_id,
            JobClusterFeatureSnapshot.eligible_for_clustering.is_(True),
        )
        .order_by(JobPosting.job_code)
    ).all()
    if not feature_rows:
        raise ClusteringError("解析运行没有可聚类特征")
    input_hash = _input_hash(parse_run, feature_rows, parameters)
    existing = db.scalar(
        select(JobClusteringRun).where(
            JobClusteringRun.job_parse_run_id == parse_run.job_parse_run_id,
            JobClusteringRun.algorithm_version == ALGORITHM_VERSION,
            JobClusteringRun.input_snapshot_hash == input_hash,
        )
    )
    if existing is not None:
        if existing.run_status_code == "success":
            return _result(existing, already_completed=True)
        if existing.run_status_code == "running":
            raise ClusteringError("相同输入的岗位聚类运行正在执行")
        existing.run_status_code = "running"
        existing.started_at = datetime.now()
        existing.completed_at = None
        existing.quality_metric_json = None
        db.commit()
        return _execute_with_failure_tracking(db, existing, feature_rows, parameters)

    run = JobClusteringRun(
        run_code=f"cluster_{uuid4().hex[:24]}",
        job_parse_run_id=parse_run.job_parse_run_id,
        run_type_code="full",
        target_date=parse_run.target_date,
        feature_version=feature_rows[0][0].feature_version,
        algorithm_name=ALGORITHM_NAME,
        algorithm_version=ALGORITHM_VERSION,
        parameter_json=parameters.as_dict(),
        input_snapshot_hash=input_hash,
        input_job_count=len(feature_rows),
        run_status_code="running",
        started_at=datetime.now(),
    )
    db.add(run)
    db.flush()
    db.commit()
    return _execute_with_failure_tracking(db, run, feature_rows, parameters)


def _execute_with_failure_tracking(
    db: Session,
    run: JobClusteringRun,
    feature_rows: list[tuple],
    parameters: ClusteringParameters,
) -> ClusteringRunResult:
    run_id = run.clustering_run_id
    try:
        return _execute_clustering_run(db, run, feature_rows, parameters)
    except Exception as exc:
        db.rollback()
        failed_run = db.get(JobClusteringRun, run_id)
        if failed_run is not None:
            failed_run.run_status_code = "failed"
            failed_run.completed_at = datetime.now()
            failed_run.quality_metric_json = {
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:1000],
            }
            db.commit()
        raise


def _execute_clustering_run(
    db: Session,
    run: JobClusteringRun,
    feature_rows: list[tuple],
    parameters: ClusteringParameters,
) -> ClusteringRunResult:

    raw_features = [_raw_feature(feature, job) for feature, job in feature_rows]
    output = cluster_jobs(raw_features, parameters)
    previous_run = db.scalar(
        select(JobClusteringRun)
        .where(
            JobClusteringRun.run_status_code == "success",
            JobClusteringRun.algorithm_version == ALGORITHM_VERSION,
            JobClusteringRun.clustering_run_id != run.clustering_run_id,
            JobClusteringRun.target_date <= run.target_date,
        )
        .order_by(JobClusteringRun.target_date.desc(), JobClusteringRun.clustering_run_id.desc())
    )
    persisted, decision_by_job = _persist_clusters(db, run, output, previous_run, parameters)
    candidate_roles = 0
    for cluster, version in persisted:
        if _propose_role(db, run, cluster, version, decision_by_job):
            candidate_roles += 1

    sizes = [len(cluster.members) for cluster, _version in persisted]
    coherences = [float(version.coherence_score or 0) for _cluster, version in persisted]
    grey_count = sum(item.status_code == "grey" for item in output.decisions)
    run.assigned_job_count = len(output.decisions) - grey_count
    run.grey_job_count = grey_count
    run.output_cluster_count = len(persisted)
    run.candidate_role_count = candidate_roles
    run.quality_metric_json = {
        "mean_coherence": round(statistics.fmean(coherences), 2) if coherences else 0,
        "singleton_cluster_count": sum(size == 1 for size in sizes),
        "singleton_job_ratio": round(sum(size == 1 for size in sizes) / len(raw_features), 6),
        "median_cluster_size": statistics.median(sizes),
        "p90_cluster_size": _percentile(sizes, 0.9),
        "grey_job_ratio": round(grey_count / len(raw_features), 6),
        "scenario_feature_status": "not_available",
        "trend_history_status": "insufficient_history",
    }
    run.run_status_code = "success"
    run.completed_at = datetime.now()
    db.commit()
    return _result(run, already_completed=False)


def review_role_version(
    db: Session,
    *,
    task: ReviewTask,
    actor_user_id: int,
    action_code: str,
    comment_text: str | None = None,
) -> JobRoleVersion:
    transitions = {
        "claim": ({"queued"}, "reviewing"),
        "approve": ({"queued", "assigned", "reviewing", "needs_revision"}, "approved"),
        "reject": ({"queued", "assigned", "reviewing", "needs_revision"}, "rejected"),
        "needs_revision": ({"queued", "assigned", "reviewing"}, "needs_revision"),
    }
    if task.queue_code != "data_review" or task.target_type_code != "job_role_version":
        raise ClusteringError("审核任务不属于岗位版本数据审核队列")
    if action_code not in transitions:
        raise ClusteringError("不支持的岗位版本审核动作")
    allowed, next_status = transitions[action_code]
    if task.task_status_code not in allowed:
        raise ClusteringError("当前岗位版本审核状态不允许执行该动作")
    version = db.get(JobRoleVersion, task.target_id)
    if version is None:
        raise ClusteringError("岗位版本审核目标不存在")
    role = db.get(JobRole, version.job_role_id)
    if role is None:
        raise ClusteringError("稳定岗位不存在")
    before = role_version_snapshot(db, version)
    previous_task_status = task.task_status_code
    task.task_status_code = next_status
    task.assigned_user_id = actor_user_id
    if action_code == "approve":
        previous = db.scalar(
            select(JobRoleVersion).where(
                JobRoleVersion.job_role_id == role.job_role_id,
                JobRoleVersion.approval_status_code == "approved",
                JobRoleVersion.valid_to.is_(None),
                JobRoleVersion.job_role_version_id != version.job_role_version_id,
            )
        )
        if previous is not None:
            if previous.valid_from >= version.valid_from:
                raise ClusteringError("新岗位版本生效日期必须晚于当前正式版本")
            previous.valid_to = version.valid_from
        version.approval_status_code = "approved"
        version.approved_by_user_id = actor_user_id
        version.approved_at = datetime.now()
        role.lifecycle_status_code = "active"
        role.approved_at = role.approved_at or datetime.now()
        events = list(
            db.scalars(
                select(JobEvolutionEvent).where(
                    JobEvolutionEvent.to_role_version_id == version.job_role_version_id
                )
            )
        )
        for event in events:
            event.approval_status_code = "approved"
    elif action_code == "reject":
        version.approval_status_code = "rejected"
        for event in db.scalars(
            select(JobEvolutionEvent).where(
                JobEvolutionEvent.to_role_version_id == version.job_role_version_id
            )
        ):
            event.approval_status_code = "rejected"
    elif action_code == "needs_revision":
        version.approval_status_code = "reviewing"
    elif action_code == "claim":
        version.approval_status_code = "reviewing"
    db.flush()
    after = role_version_snapshot(db, version)
    db.add(
        ReviewAction(
            review_task_id=task.review_task_id,
            actor_user_id=actor_user_id,
            action_code=action_code,
            from_status_code=previous_task_status,
            to_status_code=next_status,
            comment_text=comment_text,
            before_snapshot_json=before,
            after_snapshot_json=after,
        )
    )
    db.flush()
    return version


def role_version_snapshot(db: Session, version: JobRoleVersion) -> dict:
    role = db.get(JobRole, version.job_role_id)
    requirements = list(
        db.scalars(
            select(JobRoleVersionRequirement)
            .where(JobRoleVersionRequirement.job_role_version_id == version.job_role_version_id)
            .order_by(JobRoleVersionRequirement.long_term_importance_score.desc())
        )
    )
    technology_ids = [item.technology_node_id for item in requirements]
    codes = {
        node.technology_node_id: node.technology_code
        for node in db.scalars(
            select(TechnologyNode).where(TechnologyNode.technology_node_id.in_(technology_ids))
        )
    }
    return {
        "role_code": role.role_code if role else None,
        "role_name": version.role_name,
        "version_no": version.version_no,
        "valid_from": version.valid_from.isoformat(),
        "approval_status_code": version.approval_status_code,
        "evidence_strength_score": str(version.evidence_strength_score or 0),
        "requirements": [
            {
                "technology_code": codes.get(item.technology_node_id),
                "type": item.requirement_type_code,
                "importance": str(item.long_term_importance_score),
                "recent_activity": str(item.recent_activity_score),
                "trend_status": item.trend_status_code,
            }
            for item in requirements
        ],
    }


def _persist_clusters(
    db: Session,
    run: JobClusteringRun,
    output: ClusteringOutput,
    previous_run: JobClusteringRun | None,
    parameters: ClusteringParameters,
) -> tuple[list[tuple[ClusterDraft, JobClusterVersion]], dict[int, object]]:
    previous_clusters, previous_members = _previous_clusters(db, previous_run)
    matches = _continued_matches(output.clusters, previous_clusters, previous_members)
    versions_by_draft: dict[int, JobClusterVersion] = {}
    persisted = []
    decision_by_job = {item.job_posting_id: item for item in output.decisions}
    used_codes = set()
    for cluster in output.clusters:
        old_version_id, overlap = matches.get(cluster.draft_id, (None, 0.0))
        old_version = previous_clusters.get(old_version_id) if old_version_id else None
        code = old_version.stable_cluster_code if old_version else _stable_cluster_code(cluster)
        if code in used_codes:
            code = _stable_cluster_code(cluster, salt=str(cluster.draft_id))
        used_codes.add(code)
        label = _cluster_label(cluster)
        scores = [similarity(member, cluster).total for member in cluster.members]
        coherence = Decimal(str(round(statistics.fmean(scores) * 100, 2)))
        organization_count = _organization_count(
            db, [item.raw.job_posting_id for item in cluster.members]
        )
        version = JobClusterVersion(
            clustering_run_id=run.clustering_run_id,
            stable_cluster_code=code,
            cluster_label=label,
            cluster_description=(
                f"由{len(cluster.members)}条真实JD按标题、职责、技术、领域和级别的"
                "可解释稀疏特征形成。"
            ),
            member_count=len(cluster.members),
            independent_organization_count=organization_count,
            centroid_json=cluster.snapshot(),
            representative_job_ids_json=[],
            coherence_score=coherence,
            cluster_status_code=(
                "active"
                if len(cluster.members) >= 2 and coherence >= Decimal("35")
                else "needs_review"
            ),
        )
        db.add(version)
        db.flush()
        versions_by_draft[cluster.draft_id] = version
        persisted.append((cluster, version))
        if old_version:
            db.add(
                JobClusterLineage(
                    from_cluster_version_id=old_version.job_cluster_version_id,
                    to_cluster_version_id=version.job_cluster_version_id,
                    lineage_type_code="continued",
                    member_overlap_score=decimal_score(overlap),
                    explanation_text="成员Jaccard重叠达到稳定簇延续阈值。",
                )
            )
        else:
            db.add(
                JobClusterLineage(
                    to_cluster_version_id=version.job_cluster_version_id,
                    lineage_type_code="born",
                    explanation_text="本次运行未找到达到延续阈值的历史岗位簇。",
                )
            )

    for cluster, version in persisted:
        ranked_members = sorted(
            ((member, similarity(member, cluster)) for member in cluster.members),
            key=lambda item: (-item[1].total, item[0].raw.job_code),
        )
        representative_ids = {item[0].raw.job_posting_id for item in ranked_members[:3]}
        version.representative_job_ids_json = sorted(representative_ids)
        for member, own_score in ranked_members:
            decision = decision_by_job[member.raw.job_posting_id]
            external_candidates = [
                {
                    "stable_cluster_code": versions_by_draft[
                        item.cluster_draft_id
                    ].stable_cluster_code,
                    "score": item.total,
                    "breakdown": {key: round(value, 6) for key, value in item.breakdown.items()},
                }
                for item in decision.top_candidates
                if item.cluster_draft_id != cluster.draft_id
            ]
            candidates = [
                {
                    "stable_cluster_code": version.stable_cluster_code,
                    "score": own_score.total,
                    "breakdown": {
                        key: round(value, 6) for key, value in own_score.breakdown.items()
                    },
                    "selected": True,
                },
                *external_candidates,
            ]
            db.add(
                JobClusterMember(
                    job_cluster_version_id=version.job_cluster_version_id,
                    job_posting_id=member.raw.job_posting_id,
                    similarity_score=decimal_score(own_score.total),
                    assignment_method_code=ALGORITHM_VERSION,
                    assignment_status_code=decision.status_code,
                    assignment_confidence=Decimal(str(round(decision.initial_score * 100, 2))),
                    similarity_breakdown_json={
                        key: round(value, 6) for key, value in own_score.breakdown.items()
                    },
                    top_candidates_json=candidates[: parameters.top_k],
                    is_representative=member.raw.job_posting_id in representative_ids,
                )
            )
        _persist_domains(db, run, cluster, version)
    db.flush()
    return persisted, decision_by_job


def _persist_domains(
    db: Session,
    run: JobClusteringRun,
    cluster: ClusterDraft,
    version: JobClusterVersion,
) -> None:
    centroid = cluster.centroid("domain")
    if not centroid:
        return
    domains = {
        item.domain_code: item
        for item in db.scalars(select(TechnologyDomain).where(TechnologyDomain.is_active.is_(True)))
    }
    total = sum(centroid.values()) or 1
    primary = max(centroid, key=centroid.get)
    for code, value in centroid.items():
        domain = domains.get(code)
        if domain is None:
            continue
        evidence_count = sum(code in member.raw.domain_weights for member in cluster.members)
        db.add(
            JobClusterDomain(
                job_cluster_version_id=version.job_cluster_version_id,
                technology_domain_id=domain.technology_domain_id,
                domain_score=Decimal(str(round(value / total * 100, 2))),
                is_primary=code == primary,
                evidence_count=evidence_count,
                calculation_version=CALCULATION_VERSION,
            )
        )


def _propose_role(
    db: Session,
    run: JobClusteringRun,
    cluster: ClusterDraft,
    cluster_version: JobClusterVersion,
    _decision_by_job: dict[int, object],
) -> bool:
    if (
        cluster_version.cluster_status_code != "active"
        or cluster_version.member_count < 3
        or cluster_version.independent_organization_count < 2
        or cluster_version.cluster_label == "待命名岗位簇"
    ):
        return False
    prior_role_id = db.scalar(
        select(JobClusterRole.job_role_id)
        .join(
            JobClusterLineage,
            JobClusterLineage.from_cluster_version_id == JobClusterRole.job_cluster_version_id,
        )
        .where(
            JobClusterLineage.to_cluster_version_id == cluster_version.job_cluster_version_id,
            JobClusterLineage.lineage_type_code == "continued",
        )
    )
    role = db.get(JobRole, prior_role_id) if prior_role_id else None
    if role is None:
        role_name = _unique_role_name(db, cluster_version.cluster_label, cluster_version)
        role = JobRole(
            role_code=f"ROLE-{uuid4().hex[:20]}",
            canonical_name=role_name,
            normalized_name=role_name.casefold(),
            origin_type_code="cluster_derived",
            lifecycle_status_code="candidate",
            first_detected_at=datetime.now(),
        )
        db.add(role)
        db.flush()
        for alias in _representative_titles(cluster):
            normalized = alias.casefold().strip()
            if normalized:
                db.add(
                    JobRoleAlias(
                        job_role_id=role.job_role_id,
                        alias_text=alias,
                        normalized_alias=normalized,
                    )
                )
    db.add(
        JobClusterRole(
            job_cluster_version_id=cluster_version.job_cluster_version_id,
            job_role_id=role.job_role_id,
            relation_type_code="represents",
            confidence_score=cluster_version.coherence_score,
        )
    )
    previous = db.scalar(
        select(JobRoleVersion)
        .where(JobRoleVersion.job_role_id == role.job_role_id)
        .order_by(JobRoleVersion.version_no.desc())
    )
    if previous is not None and previous.valid_from >= run.target_date:
        # Same-day recalibration may remap a cluster, but must not create two role
        # versions with an impossible or backwards validity interval.
        db.flush()
        return False
    metrics = _capability_metrics(db, run, cluster)
    responsibilities = _representative_responsibilities(
        db, run.job_parse_run_id, [item.raw.job_posting_id for item in cluster.members]
    )
    version = JobRoleVersion(
        job_role_id=role.job_role_id,
        version_no=(previous.version_no + 1) if previous else 1,
        previous_version_id=previous.job_role_version_id if previous else None,
        valid_from=run.target_date,
        role_name=role.canonical_name,
        one_line_definition=(
            f"由{cluster_version.member_count}条真实JD统计归纳的{role.canonical_name}岗位版本。"
        ),
        core_responsibility_text="\n".join(responsibilities) or "当前职责证据不足，待人工补充。",
        job_level_distribution_json=dict(
            Counter(item.raw.level_code or "unknown" for item in cluster.members)
        ),
        update_summary=(
            "初始岗位版本，能力来自真实JD加权统计。"
            if previous is None
            else "基于新聚类周期生成的岗位能力更新草稿。"
        ),
        evidence_strength_score=_evidence_strength(cluster_version, metrics),
    )
    db.add(version)
    db.flush()
    requirements = []
    for metric in metrics:
        requirement = JobRoleVersionRequirement(
            job_role_version_id=version.job_role_version_id,
            technology_node_id=metric.technology_node_id,
            requirement_type_code=metric.requirement_type_code,
            long_term_importance_score=metric.long_term_importance,
            recent_activity_score=metric.recent_activity,
            coverage_rate=metric.coverage_rate,
            required_ratio=metric.required_ratio,
            trend_score=metric.trend_score,
            trend_status_code=metric.trend_status_code,
            supporting_job_count=metric.supporting_job_count,
            independent_organization_count=metric.organization_count,
            independent_source_count=metric.source_count,
            last_seen_at=metric.last_seen_at,
            confidence_score=metric.confidence_score,
        )
        db.add(requirement)
        db.flush()
        requirements.append((metric, requirement))
        for evidence_id in metric.evidence_ids:
            evidence = db.get(EvidenceSpan, evidence_id)
            organization_id = db.scalar(
                select(JobPosting.organization_id)
                .join(
                    JobRequirement,
                    JobRequirement.job_posting_id == JobPosting.job_posting_id,
                )
                .join(
                    JobRequirementEvidence,
                    JobRequirementEvidence.job_requirement_id == JobRequirement.job_requirement_id,
                )
                .where(JobRequirementEvidence.evidence_span_id == evidence_id)
                .limit(1)
            )
            if evidence is not None:
                db.add(
                    JobRoleEvidence(
                        job_role_version_id=version.job_role_version_id,
                        role_version_requirement_id=requirement.role_version_requirement_id,
                        evidence_span_id=evidence_id,
                        evidence_role_code="requirement",
                        support_score=Decimal("100"),
                        source_organization_id=organization_id,
                    )
                )
    event = _create_evolution_event(db, role, version, previous, requirements)
    snapshot = role_version_snapshot(db, version)
    db.add(
        ReviewTask(
            task_code=f"RT-{uuid4().hex[:20]}",
            queue_code="data_review",
            target_type_code="job_role_version",
            target_id=version.job_role_version_id,
            priority_score=Decimal("50"),
            target_snapshot_json=snapshot,
            reason_json={
                "codes": ["statistical_role_version_requires_review"],
                "evolution_event_code": event.event_code,
            },
        )
    )
    db.flush()
    return True


def _capability_metrics(
    db: Session, run: JobClusteringRun, cluster: ClusterDraft
) -> list[CapabilityMetric]:
    member_ids = [item.raw.job_posting_id for item in cluster.members]
    jobs = {
        item.job_posting_id: item
        for item in db.scalars(select(JobPosting).where(JobPosting.job_posting_id.in_(member_ids)))
    }
    sources: dict[int, set[int]] = defaultdict(set)
    for job_id, source_id in db.execute(
        select(JobPostingDataSource.job_posting_id, JobPostingDataSource.data_source_id).where(
            JobPostingDataSource.job_posting_id.in_(member_ids)
        )
    ):
        sources[job_id].add(source_id)
    parse_run = db.get(JobParseRun, run.job_parse_run_id)
    nodes = {
        item.technology_code: item
        for item in db.scalars(
            select(TechnologyNode).where(
                TechnologyNode.governance_status_code == "active",
                TechnologyNode.taxonomy_version_id
                == (parse_run.taxonomy_version_id if parse_run else -1),
            )
        )
    }
    required_jobs: dict[int, set[int]] = defaultdict(set)
    task_jobs: dict[int, set[int]] = defaultdict(set)
    evidence_ids: dict[int, list[int]] = defaultdict(list)
    requirement_rows = db.execute(
        select(
            JobRequirement.job_posting_id,
            JobRequirement.technology_node_id,
            JobRequirement.requirement_type_code,
            TechnologyMatchAssessment.evidence_span_id,
        )
        .join(
            TechnologyMatchAssessment,
            TechnologyMatchAssessment.job_requirement_id == JobRequirement.job_requirement_id,
        )
        .where(
            JobRequirement.job_posting_id.in_(member_ids),
            JobRequirement.technology_node_id.is_not(None),
            TechnologyMatchAssessment.job_parse_run_id == run.job_parse_run_id,
            TechnologyMatchAssessment.assessment_status_code == "accepted",
        )
    ).all()
    for job_id, technology_id, requirement_type, evidence_id in requirement_rows:
        if requirement_type == "required":
            required_jobs[technology_id].add(job_id)
        if evidence_id is not None and len(evidence_ids[technology_id]) < 20:
            evidence_ids[technology_id].append(evidence_id)
    for job_id, technology_id in db.execute(
        select(JobRequirement.job_posting_id, JobRequirement.technology_node_id)
        .join(
            TechnologyMatchAssessment,
            TechnologyMatchAssessment.job_requirement_id == JobRequirement.job_requirement_id,
        )
        .where(
            TechnologyMatchAssessment.job_parse_run_id == run.job_parse_run_id,
            TechnologyMatchAssessment.context_type_code == "responsibility",
            TechnologyMatchAssessment.assessment_status_code == "accepted",
            JobRequirement.job_posting_id.in_(member_ids),
            JobRequirement.technology_node_id.is_not(None),
        )
    ):
        task_jobs[technology_id].add(job_id)
    total_weight = sum(max(0.05, item.raw.sample_weight) for item in cluster.members)
    time_valid_jobs = [
        item
        for item in cluster.members
        if jobs[item.raw.job_posting_id].time_quality_code == "source_collected"
        and jobs[item.raw.job_posting_id].source_collected_at is not None
    ]
    date_span = (
        (
            max(jobs[item.raw.job_posting_id].source_collected_at for item in time_valid_jobs)
            - min(jobs[item.raw.job_posting_id].source_collected_at for item in time_valid_jobs)
        ).days
        if time_valid_jobs
        else 0
    )
    time_weight = sum(max(0.05, item.raw.sample_weight) for item in time_valid_jobs)
    metrics = []
    technology_codes = sorted(
        {code for item in cluster.members for code in item.raw.technology_weights}
    )
    for code in technology_codes:
        node = nodes.get(code)
        if node is None:
            continue
        supporters = [item for item in cluster.members if code in item.raw.technology_weights]
        support_weight = sum(
            max(0.05, item.raw.sample_weight) * item.raw.technology_weights[code]
            for item in supporters
        )
        coverage = support_weight / total_weight if total_weight else 0.0
        if len(supporters) < 2 and len(cluster.members) >= 5:
            continue
        if coverage < 0.08:
            continue
        required_weight = sum(
            max(0.05, item.raw.sample_weight)
            for item in supporters
            if item.raw.job_posting_id in required_jobs[node.technology_node_id]
        )
        required_ratio = min(1.0, required_weight / support_weight) if support_weight else 0.0
        organizations = {
            jobs[item.raw.job_posting_id].organization_id
            for item in supporters
            if jobs[item.raw.job_posting_id].organization_id is not None
        }
        source_ids = {
            source_id for item in supporters for source_id in sources[item.raw.job_posting_id]
        }
        recent_support_weight = sum(
            max(0.05, item.raw.sample_weight) * item.raw.technology_weights[code]
            for item in time_valid_jobs
            if code in item.raw.technology_weights
            and (run.target_date - jobs[item.raw.job_posting_id].source_collected_at.date()).days
            <= 90
        )
        recent_activity = recent_support_weight / time_weight if time_weight else 0.0
        trend_status = "insufficient_history" if date_span < 90 else "available"
        trend_score = None
        org_diversity = min(1.0, len(organizations) / 5)
        source_diversity = min(1.0, len(source_ids) / 3)
        task_support = len(task_jobs[node.technology_node_id]) / len(supporters)
        importance = 100 * (
            0.32 * coverage
            + 0.20 * required_ratio
            + 0.14 * org_diversity
            + 0.08 * source_diversity
            + 0.14 * recent_activity
            + 0.07 * 0.0
            + 0.05 * task_support
        )
        requirement_type = "required" if required_ratio >= 0.60 else "bonus"
        last_seen = max(
            (
                jobs[item.raw.job_posting_id].source_collected_at
                for item in supporters
                if jobs[item.raw.job_posting_id].time_quality_code == "source_collected"
                and jobs[item.raw.job_posting_id].source_collected_at is not None
            ),
            default=None,
        )
        confidence = min(100.0, 35 + 20 * coverage + 8 * len(organizations) + 5 * len(source_ids))
        metrics.append(
            CapabilityMetric(
                technology_node_id=node.technology_node_id,
                technology_code=code,
                requirement_type_code=requirement_type,
                long_term_importance=Decimal(str(round(importance, 2))),
                recent_activity=Decimal(str(round(recent_activity * 100, 2))),
                coverage_rate=Decimal(str(round(coverage, 6))),
                required_ratio=Decimal(str(round(required_ratio, 6))),
                trend_score=trend_score,
                trend_status_code=trend_status,
                supporting_job_count=len(supporters),
                organization_count=len(organizations),
                source_count=len(source_ids),
                last_seen_at=last_seen,
                confidence_score=Decimal(str(round(confidence, 2))),
                evidence_ids=tuple(dict.fromkeys(evidence_ids[node.technology_node_id])),
            )
        )
    return sorted(metrics, key=lambda item: (-item.long_term_importance, item.technology_code))


def _create_evolution_event(
    db: Session,
    role: JobRole,
    version: JobRoleVersion,
    previous: JobRoleVersion | None,
    requirements: list[tuple[CapabilityMetric, JobRoleVersionRequirement]],
) -> JobEvolutionEvent:
    old_requirements = {
        item.technology_node_id: item
        for item in db.scalars(
            select(JobRoleVersionRequirement).where(
                JobRoleVersionRequirement.job_role_version_id
                == (previous.job_role_version_id if previous else -1)
            )
        )
    }
    event = JobEvolutionEvent(
        event_code=f"EV-{uuid4().hex[:20]}",
        job_role_id=role.job_role_id,
        from_role_version_id=previous.job_role_version_id if previous else None,
        to_role_version_id=version.job_role_version_id,
        event_type_code="updated" if previous else "created",
        change_summary=(
            "初始岗位版本能力建议，全部变更需人工审核。"
            if previous is None
            else "新周期岗位能力统计与上一版本的差异草稿。"
        ),
        confidence_score=version.evidence_strength_score or Decimal("0"),
    )
    db.add(event)
    db.flush()
    current_ids = set()
    for metric, requirement in requirements:
        current_ids.add(metric.technology_node_id)
        old = old_requirements.get(metric.technology_node_id)
        if old is None:
            change_type, subtype = "added", None
        else:
            magnitude = abs(requirement.long_term_importance_score - old.long_term_importance_score)
            type_changed = requirement.requirement_type_code != old.requirement_type_code
            if magnitude < Decimal("10") and not type_changed:
                continue
            change_type = "modified"
            subtype = (
                "type"
                if type_changed
                else (
                    "strengthened"
                    if requirement.long_term_importance_score > old.long_term_importance_score
                    else "weakened"
                )
            )
        db.add(
            JobEvolutionChange(
                job_evolution_event_id=event.job_evolution_event_id,
                technology_node_id=metric.technology_node_id,
                change_type_code=change_type,
                change_subtype_code=subtype,
                old_value_json=_requirement_value(old) if old else None,
                new_value_json=_requirement_value(requirement),
                change_magnitude=(
                    abs(requirement.long_term_importance_score - old.long_term_importance_score)
                    if old
                    else requirement.long_term_importance_score
                ),
                change_reason=("基于当前真实JD覆盖、必需比例、独立企业和来源统计。"),
                evidence_count=len(metric.evidence_ids),
            )
        )
    # No removal is proposed until multiple sufficiently long source-time windows exist.
    return event


def _requirement_value(requirement: JobRoleVersionRequirement | None) -> dict | None:
    if requirement is None:
        return None
    return {
        "requirement_type_code": requirement.requirement_type_code,
        "long_term_importance_score": str(requirement.long_term_importance_score),
        "recent_activity_score": str(requirement.recent_activity_score),
        "coverage_rate": str(requirement.coverage_rate),
        "trend_status_code": requirement.trend_status_code,
    }


def _raw_feature(feature: JobClusterFeatureSnapshot, job: JobPosting) -> RawJobFeature:
    return RawJobFeature(
        job_posting_id=job.job_posting_id,
        job_code=job.job_code,
        title=job.job_title_normalized,
        title_tokens=_canonical_title_tokens(feature.title_tokens_json),
        responsibility_tokens=tuple(feature.responsibility_tokens_json),
        technology_weights={
            key: float(value) for key, value in feature.technology_weights_json.items()
        },
        domain_weights={key: float(value) for key, value in feature.domain_weights_json.items()},
        level_code=feature.level_code,
        sample_weight=float(feature.sample_weight),
    )


def _input_hash(
    parse_run: JobParseRun, feature_rows: list[tuple], parameters: ClusteringParameters
) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {
                "parse_input": parse_run.input_snapshot_hash,
                "algorithm": ALGORITHM_VERSION,
                "parameters": parameters.as_dict(),
            },
            sort_keys=True,
        ).encode()
    )
    for feature, job in feature_rows:
        digest.update(f"\0{job.job_code}\0{feature.feature_hash}".encode())
    return digest.hexdigest()


def _cluster_label(cluster: ClusterDraft) -> str:
    titles = [
        _display_title(item.raw.title) for item in cluster.members if _usable_title(item.raw.title)
    ]
    titles = [title for title in titles if title]
    if not titles:
        return "待命名岗位簇"
    counts = Counter(titles)
    return max(counts, key=lambda title: (counts[title], -len(title), title))[:300]


def _usable_title(title: str) -> bool:
    lowered = title.casefold().strip()
    if not lowered or "未说明岗位" in lowered or "unknown" == lowered:
        return False
    mojibake = sum(lowered.count(char) for char in ("ã", "î", "ê", "¸", "º", "æ"))
    return mojibake < 2


def _representative_titles(cluster: ClusterDraft) -> list[str]:
    return list(
        dict.fromkeys(
            _display_title(item.raw.title)
            for item in cluster.members
            if _usable_title(item.raw.title) and _display_title(item.raw.title)
        )
    )[:10]


TITLE_NOISE_TOKENS = {
    "上海",
    "深圳",
    "北京",
    "杭州",
    "广州",
    "苏州",
    "南京",
    "武汉",
    "成都",
    "重庆",
    "天津",
    "西安",
    "长沙",
    "合肥",
    "宁波",
    "东莞",
    "佛山",
    "无锡",
    "junior",
    "senior",
    "staff",
    "lead",
    "principal",
}


def _canonical_title_tokens(tokens: list[str]) -> tuple[str, ...]:
    return tuple(
        token
        for token in tokens
        if token.casefold() not in TITLE_NOISE_TOKENS
        and not re.fullmatch(r"j?\d{4,}", token.casefold())
    )


def _display_title(title: str) -> str:
    cleaned = re.sub(
        r"^(上海|深圳|北京|杭州|广州|苏州|南京|武汉|成都|重庆|天津|西安|长沙|合肥|宁波|东莞|佛山|无锡)\s+",
        "",
        title.strip(),
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\(j?\d{4,}\)$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" -—·")[:300]


def _stable_cluster_code(cluster: ClusterDraft, salt: str = "") -> str:
    members = "\0".join(sorted(item.raw.job_code for item in cluster.members))
    payload = f"{salt}:{members}"
    return f"JC-{hashlib.sha256(payload.encode()).hexdigest()[:16]}"


def _organization_count(db: Session, job_ids: list[int]) -> int:
    return (
        db.scalar(
            select(func.count(func.distinct(JobPosting.organization_id))).where(
                JobPosting.job_posting_id.in_(job_ids),
                JobPosting.organization_id.is_not(None),
            )
        )
        or 0
    )


def _previous_clusters(
    db: Session, previous_run: JobClusteringRun | None
) -> tuple[dict[int, JobClusterVersion], dict[int, set[int]]]:
    if previous_run is None:
        return {}, {}
    clusters = {
        item.job_cluster_version_id: item
        for item in db.scalars(
            select(JobClusterVersion).where(
                JobClusterVersion.clustering_run_id == previous_run.clustering_run_id
            )
        )
    }
    members: dict[int, set[int]] = defaultdict(set)
    for cluster_id, job_id in db.execute(
        select(JobClusterMember.job_cluster_version_id, JobClusterMember.job_posting_id).where(
            JobClusterMember.job_cluster_version_id.in_(clusters)
        )
    ):
        members[cluster_id].add(job_id)
    return clusters, members


def _continued_matches(
    clusters: tuple[ClusterDraft, ...],
    previous_clusters: dict[int, JobClusterVersion],
    previous_members: dict[int, set[int]],
) -> dict[int, tuple[int, float]]:
    candidates = []
    for cluster in clusters:
        current = {item.raw.job_posting_id for item in cluster.members}
        for old_id in previous_clusters:
            old = previous_members[old_id]
            overlap = len(current & old) / len(current | old) if current | old else 0.0
            if overlap >= 0.55:
                candidates.append((overlap, cluster.draft_id, old_id))
    matches = {}
    used_old = set()
    for overlap, draft_id, old_id in sorted(candidates, reverse=True):
        if draft_id not in matches and old_id not in used_old:
            matches[draft_id] = (old_id, overlap)
            used_old.add(old_id)
    return matches


def _unique_role_name(db: Session, label: str, cluster_version: JobClusterVersion) -> str:
    primary_domain = db.scalar(
        select(TechnologyDomain.domain_code)
        .join(
            JobClusterDomain,
            JobClusterDomain.technology_domain_id == TechnologyDomain.technology_domain_id,
        )
        .where(
            JobClusterDomain.job_cluster_version_id == cluster_version.job_cluster_version_id,
            JobClusterDomain.is_primary.is_(True),
        )
    )
    candidate = f"{label} · {primary_domain}" if primary_domain else label
    if not db.scalar(select(JobRole).where(JobRole.normalized_name == candidate.casefold())):
        return candidate[:300]
    return f"{candidate} · {cluster_version.stable_cluster_code[-6:]}"[:300]


def _representative_responsibilities(
    db: Session, parse_run_id: int, job_ids: list[int]
) -> list[str]:
    rows = db.scalars(
        select(JobResponsibility.normalized_task_text)
        .where(
            JobResponsibility.job_parse_run_id == parse_run_id,
            JobResponsibility.job_posting_id.in_(job_ids),
            JobResponsibility.normalized_task_text.is_not(None),
        )
        .order_by(
            JobResponsibility.confidence_score.desc(), JobResponsibility.job_responsibility_id
        )
        .limit(30)
    )
    return [text[:500] for text in dict.fromkeys(rows) if text][:5]


def _evidence_strength(
    cluster_version: JobClusterVersion, metrics: list[CapabilityMetric]
) -> Decimal:
    if not metrics:
        return Decimal("0")
    average_confidence = statistics.fmean(float(item.confidence_score) for item in metrics)
    support = min(100.0, cluster_version.member_count / 10 * 100)
    diversity = min(100.0, cluster_version.independent_organization_count / 5 * 100)
    return Decimal(str(round(0.45 * average_confidence + 0.30 * support + 0.25 * diversity, 2)))


def _percentile(values: list[int], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * percentile)))
    return ordered[index]


def _result(run: JobClusteringRun, *, already_completed: bool) -> ClusteringRunResult:
    return ClusteringRunResult(
        run_code=run.run_code,
        input_job_count=run.input_job_count,
        cluster_count=run.output_cluster_count,
        grey_job_count=run.grey_job_count,
        candidate_role_count=run.candidate_role_count,
        already_completed=already_completed,
    )
