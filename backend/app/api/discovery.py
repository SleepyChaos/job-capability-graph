from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.data_center import get_reviewer
from app.db.session import get_db
from app.modules.data_center.models import AppUser, ReviewTask
from app.modules.discovery.models import DiscoveryRun, EmergingRoleCandidate, StandardJobDescription
from app.modules.discovery.service import (
    DiscoveryError,
    apply_candidate_expression,
    candidate_snapshot,
    review_candidate,
    run_discovery,
)

router = APIRouter(tags=["new-role-discovery"])


class DiscoveryRunCreate(BaseModel):
    mode_code: Literal["automatic", "technology_directed", "name_inference"]
    target_date: date
    selected_technology_ids: list[int] = Field(default_factory=list, max_length=20)
    query_role_name: str | None = Field(default=None, max_length=500)
    query_description: str | None = Field(default=None, max_length=5000)
    parameters: dict | None = None


class DiscoveryRunResponse(BaseModel):
    run_code: str
    mode_code: str
    target_date: date
    run_status_code: str
    candidate_count: int
    task_count: int
    evidence_limited: bool
    already_completed: bool = False


class CandidateListItem(BaseModel):
    candidate_code: str
    proposed_name: str
    maturity_stage_code: str
    workflow_status_code: str
    candidate_score: Decimal
    classification_code: str
    risk_flags: list
    run_code: str


class CandidatePage(BaseModel):
    total: int
    items: list[CandidateListItem]


class CandidateDetail(BaseModel):
    candidate: dict
    run: dict
    review_task_code: str | None
    standard_jds: list[dict]


class CandidateReviewAction(BaseModel):
    action_code: Literal["claim", "approve", "reject", "needs_revision"]
    comment_text: str | None = None


class CandidateExpressionUpdate(BaseModel):
    proposed_name: str = Field(min_length=1, max_length=500)
    one_line_definition: str = Field(min_length=1, max_length=3000)
    core_responsibilities: list[str] = Field(min_length=1, max_length=20)
    formation_reason: str = Field(min_length=1, max_length=5000)
    difference_explanation: str = Field(min_length=1, max_length=5000)
    fact_references: list[str] = Field(min_length=1, max_length=200)
    model_version: str = Field(min_length=1, max_length=100)


@router.post("/role-discovery/runs", response_model=DiscoveryRunResponse, status_code=201)
def create_discovery_run(payload: DiscoveryRunCreate, db: Annotated[Session, Depends(get_db)]):
    try:
        result = run_discovery(
            db,
            mode_code=payload.mode_code,
            target_date=payload.target_date,
            selected_technology_ids=payload.selected_technology_ids,
            query_role_name=payload.query_role_name,
            query_description=payload.query_description,
            parameters=payload.parameters,
        )
    except DiscoveryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    run = db.scalar(select(DiscoveryRun).where(DiscoveryRun.run_code == result.run_code))
    return DiscoveryRunResponse(
        run_code=result.run_code,
        mode_code=run.mode_code,
        target_date=run.target_date,
        run_status_code=run.run_status_code,
        candidate_count=result.candidate_count,
        task_count=result.task_count,
        evidence_limited=result.evidence_limited,
        already_completed=result.already_completed,
    )


@router.get("/role-discovery/runs", response_model=list[DiscoveryRunResponse])
def list_discovery_runs(
    db: Annotated[Session, Depends(get_db)],
    mode_code: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    query = select(DiscoveryRun).order_by(DiscoveryRun.created_at.desc()).limit(limit)
    if mode_code:
        query = query.where(DiscoveryRun.mode_code == mode_code)
    rows = list(db.scalars(query))
    return [
        DiscoveryRunResponse(
            run_code=row.run_code,
            mode_code=row.mode_code,
            target_date=row.target_date,
            run_status_code=row.run_status_code,
            candidate_count=int((row.result_summary_json or {}).get("candidate_count", 0)),
            task_count=int((row.result_summary_json or {}).get("task_count", 0)),
            evidence_limited=bool((row.result_summary_json or {}).get("evidence_limited", True)),
        )
        for row in rows
    ]


@router.get("/role-discovery/candidates", response_model=CandidatePage)
def list_candidates(
    db: Annotated[Session, Depends(get_db)],
    workflow_status: str | None = None,
    maturity_stage: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    filters = []
    if workflow_status:
        filters.append(EmergingRoleCandidate.workflow_status_code == workflow_status)
    if maturity_stage:
        filters.append(EmergingRoleCandidate.maturity_stage_code == maturity_stage)
    total = db.scalar(select(func.count()).select_from(EmergingRoleCandidate).where(*filters)) or 0
    rows = db.execute(
        select(EmergingRoleCandidate, DiscoveryRun)
        .join(DiscoveryRun, DiscoveryRun.discovery_run_id == EmergingRoleCandidate.discovery_run_id)
        .where(*filters)
        .order_by(
            EmergingRoleCandidate.candidate_score.desc(), EmergingRoleCandidate.created_at.desc()
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return CandidatePage(
        total=total,
        items=[
            CandidateListItem(
                candidate_code=candidate.candidate_code,
                proposed_name=candidate.proposed_name,
                maturity_stage_code=candidate.maturity_stage_code,
                workflow_status_code=candidate.workflow_status_code,
                candidate_score=candidate.candidate_score,
                classification_code=candidate.classification_code,
                risk_flags=candidate.risk_flags_json,
                run_code=run.run_code,
            )
            for candidate, run in rows
        ],
    )


@router.get("/role-discovery/candidates/{candidate_code}", response_model=CandidateDetail)
def get_candidate(candidate_code: str, db: Annotated[Session, Depends(get_db)]):
    row = db.execute(
        select(EmergingRoleCandidate, DiscoveryRun)
        .join(DiscoveryRun, DiscoveryRun.discovery_run_id == EmergingRoleCandidate.discovery_run_id)
        .where(EmergingRoleCandidate.candidate_code == candidate_code)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="新岗位候选不存在")
    candidate, run = row
    task_code = db.scalar(
        select(ReviewTask.task_code).where(
            ReviewTask.queue_code == "job_discovery",
            ReviewTask.target_type_code == "emerging_role",
            ReviewTask.target_id == candidate.emerging_role_candidate_id,
        )
    )
    standard_jds = list(
        db.scalars(
            select(StandardJobDescription).where(
                StandardJobDescription.emerging_role_candidate_id
                == candidate.emerging_role_candidate_id
            )
        )
    )
    return CandidateDetail(
        candidate=candidate_snapshot(db, candidate),
        run={
            "run_code": run.run_code,
            "mode_code": run.mode_code,
            "target_date": run.target_date.isoformat(),
            "input_snapshot": run.input_snapshot_json,
            "result_summary": run.result_summary_json,
        },
        review_task_code=task_code,
        standard_jds=[
            {
                "standard_jd_code": item.standard_jd_code,
                "version_no": item.version_no,
                "title": item.title_text,
                "content": item.content_json,
                "is_market_evidence": item.is_market_evidence,
            }
            for item in standard_jds
        ],
    )


@router.post("/role-discovery/reviews/{task_code}/actions", response_model=dict)
def act_on_candidate_review(
    task_code: str,
    payload: CandidateReviewAction,
    db: Annotated[Session, Depends(get_db)],
    reviewer: Annotated[AppUser, Depends(get_reviewer)],
):
    try:
        candidate = review_candidate(
            db,
            task_code=task_code,
            action_code=payload.action_code,
            actor_user_id=reviewer.user_id,
            comment_text=payload.comment_text,
        )
    except DiscoveryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return candidate_snapshot(db, candidate)


@router.put("/role-discovery/candidates/{candidate_code}/expression", response_model=dict)
def update_candidate_expression(
    candidate_code: str,
    payload: CandidateExpressionUpdate,
    db: Annotated[Session, Depends(get_db)],
    _reviewer: Annotated[AppUser, Depends(get_reviewer)],
):
    try:
        candidate = apply_candidate_expression(
            db,
            candidate_code=candidate_code,
            proposed_name=payload.proposed_name,
            one_line_definition=payload.one_line_definition,
            core_responsibilities=payload.core_responsibilities,
            formation_reason=payload.formation_reason,
            difference_explanation=payload.difference_explanation,
            fact_references=payload.fact_references,
            model_version=payload.model_version,
        )
    except DiscoveryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return candidate_snapshot(db, candidate)
