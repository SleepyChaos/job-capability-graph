from decimal import Decimal
from typing import Annotated, Literal
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from app.api.data_center import get_reviewer
from app.db.session import get_db
from app.modules.clustering.algorithm import ClusteringParameters
from app.modules.clustering.models import (
    JobClusterDomain,
    JobClusteringRun,
    JobClusterMember,
    JobClusterRole,
    JobClusterVersion,
    JobEvolutionChange,
    JobEvolutionEvent,
    JobRole,
    JobRoleVersion,
    JobRoleVersionRequirement,
)
from app.modules.clustering.service import (
    ClusteringError,
    review_role_version,
    role_version_snapshot,
    run_full_clustering,
)
from app.modules.data_center.models import AppUser, ReviewTask
from app.modules.job.models import JobPosting, JobRequirement, SourceDocumentVersion
from app.modules.taxonomy.models import TechnologyDomain, TechnologyNode

router = APIRouter(tags=["job-clustering"])


# 默认值一律从 ClusteringParameters 取，不在这里重述字面量——同一个默认值曾经分散在
# 算法、CLI、API 三处，改了算法层而漏改入口层导致标定结果实际没生效。
_DEFAULTS = ClusteringParameters()


class ClusteringRunCreate(BaseModel):
    parse_run_code: str
    assign_threshold: float = Field(default=_DEFAULTS.assign_threshold, ge=0, le=1)
    grey_threshold: float = Field(default=_DEFAULTS.grey_threshold, ge=0, le=1)
    top_k: int = Field(default=_DEFAULTS.top_k, ge=1, le=10)
    max_cluster_size: int = Field(default=_DEFAULTS.max_cluster_size, ge=2, le=1000)
    # 低信息量过滤门槛：0 表示不过滤（用于与旧行为做对照）。
    min_technology_evidence_count: int = Field(
        default=_DEFAULTS.min_technology_evidence_count, ge=0, le=50
    )
    # 迭代重分配轮次：0 表示关闭，退回单遍贪心。
    max_reassign_rounds: int = Field(default=_DEFAULTS.max_reassign_rounds, ge=0, le=50)


class ClusteringRunResponse(BaseModel):
    run_code: str
    target_date: str
    algorithm_version: str
    input_job_count: int
    assigned_job_count: int
    grey_job_count: int
    output_cluster_count: int
    candidate_role_count: int
    quality_metrics: dict | None
    run_status_code: str
    already_completed: bool = False


class ClusterListItem(BaseModel):
    stable_cluster_code: str
    label: str
    member_count: int
    organization_count: int
    coherence_score: Decimal | None
    status: str
    primary_domain_code: str | None
    candidate_role_code: str | None


class ClusterPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ClusterListItem]


class ClusterMemberItem(BaseModel):
    job_code: str
    title: str
    company: str | None
    source_collected_at_date: str | None
    technology_evidence_count: int
    similarity_score: Decimal
    assignment_status: str
    assignment_confidence: Decimal | None
    is_representative: bool
    top_candidates: list


class ClusterCapabilityRankingItem(BaseModel):
    technology_code: str
    technology_name: str
    requirement_type: str
    supporting_job_count: int
    organization_count: int
    importance_weight: Decimal
    coverage_rate: Decimal | None


class ClusterDetail(ClusterListItem):
    description: str | None
    centroid: dict
    members: list[ClusterMemberItem]
    capability_rankings: list[ClusterCapabilityRankingItem]
    grey_zone_member_count: int
    grey_zone_representative_titles: list[str]


class RoleListItem(BaseModel):
    role_code: str
    canonical_name: str
    lifecycle_status: str
    latest_version_no: int | None
    latest_approval_status: str | None
    requirement_count: int


class RolePage(BaseModel):
    total: int
    items: list[RoleListItem]


class RoleRequirementItem(BaseModel):
    technology_code: str
    technology_name: str
    requirement_type: str
    importance: Decimal
    recent_activity: Decimal
    coverage_rate: Decimal | None
    required_ratio: Decimal | None
    trend_score: Decimal | None
    trend_status: str
    supporting_job_count: int
    organization_count: int
    source_count: int
    confidence: Decimal


class RoleVersionItem(BaseModel):
    version_no: int
    valid_from: str
    valid_to: str | None
    approval_status: str
    evidence_strength: Decimal | None
    update_summary: str | None


class RoleDetail(RoleListItem):
    definition: str | None
    core_responsibilities: str | None
    versions: list[RoleVersionItem]
    requirements: list[RoleRequirementItem]
    evolution_changes: list[dict]
    evolution_warning: str | None = None


class RoleReviewAction(BaseModel):
    action_code: Literal["claim", "approve", "reject", "needs_revision"]
    comment_text: str | None = None


@router.post("/job-clustering/runs", response_model=ClusteringRunResponse, status_code=201)
def create_clustering_run(payload: ClusteringRunCreate, db: Annotated[Session, Depends(get_db)]):
    if payload.grey_threshold >= payload.assign_threshold:
        raise HTTPException(status_code=422, detail="灰区门槛必须低于自动归属门槛")
    try:
        result = run_full_clustering(
            db,
            parse_run_code=payload.parse_run_code,
            parameters=ClusteringParameters(
                assign_threshold=payload.assign_threshold,
                grey_threshold=payload.grey_threshold,
                top_k=payload.top_k,
                max_cluster_size=payload.max_cluster_size,
                min_technology_evidence_count=payload.min_technology_evidence_count,
                max_reassign_rounds=payload.max_reassign_rounds,
            ),
        )
    except ClusteringError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    run = db.scalar(select(JobClusteringRun).where(JobClusteringRun.run_code == result.run_code))
    return _run_response(run, result.already_completed)


@router.get("/job-clustering/runs", response_model=list[ClusteringRunResponse])
def list_clustering_runs(db: Annotated[Session, Depends(get_db)]):
    return [
        _run_response(item)
        for item in db.scalars(
            select(JobClusteringRun).order_by(
                JobClusteringRun.target_date.desc(), JobClusteringRun.clustering_run_id.desc()
            )
        )
    ]


@router.get("/job-clusters", response_model=ClusterPage)
def list_clusters(
    db: Annotated[Session, Depends(get_db)],
    run_code: str | None = None,
    status: str | None = None,
    domain_code: str | None = None,
    min_members: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    run = _resolve_run(db, run_code)
    primary_domain = _primary_domain_subquery()
    role = _cluster_role_subquery()
    filters = [
        JobClusterVersion.clustering_run_id == run.clustering_run_id,
        JobClusterVersion.member_count >= min_members,
    ]
    if status:
        filters.append(JobClusterVersion.cluster_status_code == status)
    if domain_code:
        filters.append(primary_domain.c.primary_domain_code == domain_code)
    base = (
        select(
            JobClusterVersion,
            primary_domain.c.primary_domain_code,
            role.c.role_code,
        )
        .outerjoin(
            primary_domain,
            primary_domain.c.domain_cluster_id == JobClusterVersion.job_cluster_version_id,
        )
        .outerjoin(
            role,
            role.c.role_cluster_id == JobClusterVersion.job_cluster_version_id,
        )
        .where(*filters)
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.execute(
        base.order_by(JobClusterVersion.member_count.desc(), JobClusterVersion.cluster_label)
        .offset(offset)
        .limit(limit)
    ).all()
    return ClusterPage(
        total=total,
        limit=limit,
        offset=offset,
        items=[_cluster_item(cluster, domain, role_code) for cluster, domain, role_code in rows],
    )


@router.get("/job-clusters/{stable_cluster_code}", response_model=ClusterDetail)
def cluster_detail(
    stable_cluster_code: str,
    db: Annotated[Session, Depends(get_db)],
    run_code: str | None = None,
):
    run = _resolve_run(db, run_code)
    cluster = db.scalar(
        select(JobClusterVersion).where(
            JobClusterVersion.clustering_run_id == run.clustering_run_id,
            JobClusterVersion.stable_cluster_code == stable_cluster_code,
        )
    )
    if cluster is None:
        raise HTTPException(status_code=404, detail="岗位聚类不存在")
    domain = db.scalar(
        select(TechnologyDomain.domain_code)
        .join(
            JobClusterDomain,
            JobClusterDomain.technology_domain_id == TechnologyDomain.technology_domain_id,
        )
        .where(
            JobClusterDomain.job_cluster_version_id == cluster.job_cluster_version_id,
            JobClusterDomain.is_primary.is_(True),
        )
    )
    role_code = db.scalar(
        select(JobRole.role_code)
        .join(JobClusterRole, JobClusterRole.job_role_id == JobRole.job_role_id)
        .where(JobClusterRole.job_cluster_version_id == cluster.job_cluster_version_id)
    )
    rows = db.execute(
        select(JobClusterMember, JobPosting)
        .join(JobPosting, JobPosting.job_posting_id == JobClusterMember.job_posting_id)
        .where(JobClusterMember.job_cluster_version_id == cluster.job_cluster_version_id)
        .order_by(
            JobClusterMember.is_representative.desc(), JobClusterMember.similarity_score.desc()
        )
    ).all()

    job_posting_ids = [job.job_posting_id for _, job in rows]
    evidence_count_map: dict[int, int] = {}
    if job_posting_ids:
        ev_rows = db.execute(
            select(
                JobRequirement.job_posting_id,
                func.count(JobRequirement.job_requirement_id),
            )
            .where(JobRequirement.job_posting_id.in_(job_posting_ids))
            .group_by(JobRequirement.job_posting_id)
        ).all()
        for jid, cnt in ev_rows:
            evidence_count_map[jid] = cnt

    collected_date_map: dict[int, str | None] = {}
    if job_posting_ids:
        sd_rows = db.execute(
            select(
                JobPosting.job_posting_id,
                SourceDocumentVersion.collected_at,
                JobPosting.published_at,
                JobPosting.source_collected_at,
            )
            .outerjoin(
                SourceDocumentVersion,
                SourceDocumentVersion.source_document_version_id == JobPosting.source_document_version_id,
            )
            .where(JobPosting.job_posting_id.in_(job_posting_ids))
        ).all()
        for jid, sdv_collected_at, published_at, src_collected_at in sd_rows:
            dt = None
            if src_collected_at is not None:
                dt = src_collected_at.date()
            elif sdv_collected_at is not None:
                dt = sdv_collected_at.date()
            elif published_at is not None:
                dt = published_at.date()
            collected_date_map[jid] = dt.strftime("%Y-%m-%d") if dt is not None else None

    grey_zone_members = [(m, j) for m, j in rows if m.assignment_status_code in ('grey_zone', 'boundary', 'uncertain')]
    grey_zone_member_count = len(grey_zone_members)
    grey_zone_representative_titles = [
        j.job_title_raw for m, j in sorted(
            grey_zone_members,
            key=lambda x: (not x[0].is_representative, -float(x[0].similarity_score or 0))
        )[:3]
    ]

    capability_rankings: list[ClusterCapabilityRankingItem] = []
    if role_code:
        role = db.scalar(select(JobRole).where(JobRole.role_code == role_code))
        if role:
            latest_version = db.scalar(
                select(JobRoleVersion)
                .where(JobRoleVersion.job_role_id == role.job_role_id)
                .order_by(JobRoleVersion.version_no.desc())
            )
            if latest_version:
                req_rows = db.execute(
                    select(JobRoleVersionRequirement, TechnologyNode)
                    .join(
                        TechnologyNode,
                        TechnologyNode.technology_node_id == JobRoleVersionRequirement.technology_node_id,
                    )
                    .where(JobRoleVersionRequirement.job_role_version_id == latest_version.job_role_version_id)
                    .order_by(JobRoleVersionRequirement.long_term_importance_score.desc())
                ).all()
                for req, node in req_rows:
                    capability_rankings.append(ClusterCapabilityRankingItem(
                        technology_code=node.technology_code,
                        technology_name=node.technology_name,
                        requirement_type=req.requirement_type_code,
                        supporting_job_count=req.supporting_job_count,
                        organization_count=req.independent_organization_count,
                        importance_weight=req.long_term_importance_score,
                        coverage_rate=req.coverage_rate,
                    ))

    assigned_members = [(m, j) for m, j in rows if m.assignment_status_code not in ('grey_zone', 'boundary', 'uncertain')]
    assigned_members = assigned_members[:20]

    item = _cluster_item(cluster, domain, role_code)
    return ClusterDetail(
        **item.model_dump(),
        description=cluster.cluster_description,
        centroid=cluster.centroid_json,
        members=[
            ClusterMemberItem(
                job_code=job.job_code,
                title=job.job_title_raw,
                company=job.company_name_raw,
                source_collected_at_date=collected_date_map.get(job.job_posting_id),
                technology_evidence_count=evidence_count_map.get(job.job_posting_id, 0),
                similarity_score=member.similarity_score,
                assignment_status=member.assignment_status_code,
                assignment_confidence=member.assignment_confidence,
                is_representative=member.is_representative,
                top_candidates=member.top_candidates_json,
            )
            for member, job in assigned_members
        ],
        capability_rankings=capability_rankings,
        grey_zone_member_count=grey_zone_member_count,
        grey_zone_representative_titles=grey_zone_representative_titles,
    )


@router.get("/job-roles", response_model=RolePage)
def list_roles(
    db: Annotated[Session, Depends(get_db)],
    lifecycle_status: str | None = None,
):
    filters = [JobRole.lifecycle_status_code == lifecycle_status] if lifecycle_status else []
    roles = list(db.scalars(select(JobRole).where(*filters).order_by(JobRole.canonical_name)))
    return RolePage(total=len(roles), items=[_role_item(db, role) for role in roles])


@router.get("/job-roles/{role_code}", response_model=RoleDetail)
def role_detail(role_code: str, db: Annotated[Session, Depends(get_db)]):
    role = db.scalar(select(JobRole).where(JobRole.role_code == role_code))
    if role is None:
        raise HTTPException(status_code=404, detail="稳定岗位不存在")
    versions = list(
        db.scalars(
            select(JobRoleVersion)
            .where(JobRoleVersion.job_role_id == role.job_role_id)
            .order_by(JobRoleVersion.version_no.desc())
        )
    )
    latest = versions[0] if versions else None
    requirements = []
    if latest:
        requirements = [
            RoleRequirementItem(
                technology_code=node.technology_code,
                technology_name=node.technology_name,
                requirement_type=req.requirement_type_code,
                importance=req.long_term_importance_score,
                recent_activity=req.recent_activity_score,
                coverage_rate=req.coverage_rate,
                required_ratio=req.required_ratio,
                trend_score=req.trend_score,
                trend_status=req.trend_status_code,
                supporting_job_count=req.supporting_job_count,
                organization_count=req.independent_organization_count,
                source_count=req.independent_source_count,
                confidence=req.confidence_score,
            )
            for req, node in db.execute(
                select(JobRoleVersionRequirement, TechnologyNode)
                .join(
                    TechnologyNode,
                    TechnologyNode.technology_node_id
                    == JobRoleVersionRequirement.technology_node_id,
                )
                .where(JobRoleVersionRequirement.job_role_version_id == latest.job_role_version_id)
                .order_by(JobRoleVersionRequirement.long_term_importance_score.desc())
            )
        ]
    changes = []
    if latest:
        changes = [
            {
                "technology_code": code,
                "change_type": change.change_type_code,
                "change_subtype": change.change_subtype_code,
                "magnitude": str(change.change_magnitude or 0),
                "reason": change.change_reason,
            }
            for change, code in db.execute(
                select(JobEvolutionChange, TechnologyNode.technology_code)
                .join(
                    JobEvolutionEvent,
                    JobEvolutionEvent.job_evolution_event_id
                    == JobEvolutionChange.job_evolution_event_id,
                )
                .outerjoin(
                    TechnologyNode,
                    TechnologyNode.technology_node_id == JobEvolutionChange.technology_node_id,
                )
                .where(JobEvolutionEvent.to_role_version_id == latest.job_role_version_id)
            )
        ]
    item = _role_item(db, role)
    evolution_warning = None
    if latest:
        latest_event = db.scalar(
            select(JobEvolutionEvent)
            .where(JobEvolutionEvent.to_role_version_id == latest.job_role_version_id)
            .order_by(JobEvolutionEvent.job_evolution_event_id.desc())
        )
        evolution_warning = latest_event.comparison_warning_text if latest_event else None
    return RoleDetail(
        **item.model_dump(),
        definition=latest.one_line_definition if latest else None,
        core_responsibilities=latest.core_responsibility_text if latest else None,
        versions=[
            RoleVersionItem(
                version_no=version.version_no,
                valid_from=version.valid_from.isoformat(),
                valid_to=version.valid_to.isoformat() if version.valid_to else None,
                approval_status=version.approval_status_code,
                evidence_strength=version.evidence_strength_score,
                update_summary=version.update_summary,
            )
            for version in versions
        ],
        requirements=requirements,
        evolution_changes=changes,
        evolution_warning=evolution_warning,
    )


@router.post(
    "/job-roles/reviews/{task_code}/actions",
    response_model=dict,
)
def review_role(
    task_code: str,
    payload: RoleReviewAction,
    db: Annotated[Session, Depends(get_db)],
    reviewer: Annotated[AppUser, Depends(get_reviewer)],
):
    task = db.scalar(select(ReviewTask).where(ReviewTask.task_code == task_code))
    if task is None:
        raise HTTPException(status_code=404, detail="岗位版本审核任务不存在")
    try:
        version = review_role_version(
            db,
            task=task,
            actor_user_id=reviewer.user_id,
            action_code=payload.action_code,
            comment_text=payload.comment_text,
        )
    except ClusteringError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return role_version_snapshot(db, version)


def _resolve_run(db: Session, run_code: str | None) -> JobClusteringRun:
    statement = select(JobClusteringRun).where(JobClusteringRun.run_status_code == "success")
    if run_code:
        statement = statement.where(JobClusteringRun.run_code == run_code)
    run = db.scalar(
        statement.order_by(
            JobClusteringRun.target_date.desc(), JobClusteringRun.clustering_run_id.desc()
        )
    )
    if run is None:
        raise HTTPException(status_code=404, detail="没有可用的岗位聚类运行")
    return run


def _run_response(run: JobClusteringRun, already_completed: bool = False):
    return ClusteringRunResponse(
        run_code=run.run_code,
        target_date=run.target_date.isoformat(),
        algorithm_version=run.algorithm_version,
        input_job_count=run.input_job_count,
        assigned_job_count=run.assigned_job_count,
        grey_job_count=run.grey_job_count,
        output_cluster_count=run.output_cluster_count,
        candidate_role_count=run.candidate_role_count,
        quality_metrics=run.quality_metric_json,
        run_status_code=run.run_status_code,
        already_completed=already_completed,
    )


def _primary_domain_subquery():
    return (
        select(
            JobClusterDomain.job_cluster_version_id.label("domain_cluster_id"),
            TechnologyDomain.domain_code.label("primary_domain_code"),
        )
        .join(
            TechnologyDomain,
            TechnologyDomain.technology_domain_id == JobClusterDomain.technology_domain_id,
        )
        .where(JobClusterDomain.is_primary.is_(True))
        .subquery()
    )


def _cluster_role_subquery():
    return (
        select(
            JobClusterRole.job_cluster_version_id.label("role_cluster_id"),
            JobRole.role_code.label("role_code"),
        )
        .join(JobRole, JobRole.job_role_id == JobClusterRole.job_role_id)
        .where(JobClusterRole.is_primary.is_(True))
        .subquery()
    )


def _cluster_item(
    cluster: JobClusterVersion, domain: str | None, role_code: str | None
) -> ClusterListItem:
    return ClusterListItem(
        stable_cluster_code=cluster.stable_cluster_code,
        label=cluster.cluster_label,
        member_count=cluster.member_count,
        organization_count=cluster.independent_organization_count,
        coherence_score=cluster.coherence_score,
        status=cluster.cluster_status_code,
        primary_domain_code=domain,
        candidate_role_code=role_code,
    )


def _role_item(db: Session, role: JobRole) -> RoleListItem:
    latest = db.scalar(
        select(JobRoleVersion)
        .where(JobRoleVersion.job_role_id == role.job_role_id)
        .order_by(JobRoleVersion.version_no.desc())
    )
    requirement_count = (
        db.scalar(
            select(func.count())
            .select_from(JobRoleVersionRequirement)
            .where(
                JobRoleVersionRequirement.job_role_version_id
                == (latest.job_role_version_id if latest else -1)
            )
        )
        or 0
    )
    return RoleListItem(
        role_code=role.role_code,
        canonical_name=role.canonical_name,
        lifecycle_status=role.lifecycle_status_code,
        latest_version_no=latest.version_no if latest else None,
        latest_approval_status=latest.approval_status_code if latest else None,
        requirement_count=requirement_count,
    )
