from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.data_center import get_reviewer
from app.db.session import get_db
from app.modules.clustering.models import JobRole
from app.modules.data_center.models import AppUser, ReviewTask
from app.modules.discovery.models import DiscoveryRun, EmergingRoleCandidate, StandardJobDescription
from app.modules.discovery.service import (
    DiscoveryError,
    apply_candidate_expression,
    auto_candidate_expression,
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
    support_job_count: int
    classification_code: str
    risk_flags: list
    run_code: str
    # 缺口分级只有外部证据类（研究侧/里程碑）才有——它衡量的是「这个组合在招聘
    # 市场上从未共现」这件事有多可信。库内四类的参照系是自产岗位库，没有这个量，
    # 因此为 None，而不是补一个看起来同类、实则不同义的值。
    gap_grade: str | None = None
    # 已入库候选对应的正式岗位。发现库要回答「这条已经变成哪个岗位了」，
    # 只给候选编码不够——审阅者需要能对上岗位库里的那一条。
    approved_role_code: str | None = None
    approved_role_name: str | None = None
    approved_at: str | None = None


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


@router.get("/role-discovery/runs/{run_code}", response_model=dict)
def get_discovery_run(run_code: str, db: Annotated[Session, Depends(get_db)]):
    run = db.scalar(select(DiscoveryRun).where(DiscoveryRun.run_code == run_code))
    if run is None:
        raise HTTPException(status_code=404, detail="推演运行不存在")
    return {
        "run_code": run.run_code,
        "mode_code": run.mode_code,
        "target_date": run.target_date.isoformat(),
        "run_status_code": run.run_status_code,
        "query_role_name": run.query_role_name,
        "input_snapshot": run.input_snapshot_json,
        "result_summary": run.result_summary_json,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def _candidate_ordering(sort: str):
    if sort == "support":
        return (
            EmergingRoleCandidate.support_job_count.desc(),
            EmergingRoleCandidate.candidate_score.desc(),
            EmergingRoleCandidate.candidate_code,
        )
    return (
        EmergingRoleCandidate.candidate_score.desc(),
        EmergingRoleCandidate.created_at.desc(),
    )


@router.get("/role-discovery/candidates", response_model=CandidatePage)
def list_candidates(
    db: Annotated[Session, Depends(get_db)],
    workflow_status: str | None = None,
    maturity_stage: str | None = None,
    run_code: str | None = None,
    sort: Literal["score", "support"] = "score",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """列出岗位候选。

    `sort` 决定排序目标，二者服务于不同问题，不可互相替代：

    - `score`（默认）按证据门控评分排，回答「哪个候选更可能是正在涌现的新岗位」，
      评分中权重最高的是学术—产业落差；
    - `support` 按支撑 JD 数排，回答「哪个候选对应一个已经真实存在的岗位」。
      留出重发现实验中，同一批候选换成该排序后 Recall@10 从 81.2% 升到上界 95.8%，
      因为该任务问的正是后一个问题。
    """
    filters = []
    if workflow_status:
        filters.append(EmergingRoleCandidate.workflow_status_code == workflow_status)
    if maturity_stage:
        filters.append(EmergingRoleCandidate.maturity_stage_code == maturity_stage)
    if run_code:
        filters.append(DiscoveryRun.run_code == run_code)
    # 计数与取数必须走同一套 join，否则按 run_code 过滤时计数会退化成笛卡尔积。
    total = (
        db.scalar(
            select(func.count())
            .select_from(EmergingRoleCandidate)
            .join(
                DiscoveryRun,
                DiscoveryRun.discovery_run_id == EmergingRoleCandidate.discovery_run_id,
            )
            .where(*filters)
        )
        or 0
    )
    rows = db.execute(
        select(EmergingRoleCandidate, DiscoveryRun)
        .join(DiscoveryRun, DiscoveryRun.discovery_run_id == EmergingRoleCandidate.discovery_run_id)
        .where(*filters)
        .order_by(*_candidate_ordering(sort))
        .limit(limit)
        .offset(offset)
    ).all()
    # 已入库候选对应的岗位一次取齐，避免逐条查库。
    role_ids = {
        candidate.approved_job_role_id
        for candidate, _ in rows
        if candidate.approved_job_role_id
    }
    roles: dict[int, tuple[str, str]] = {}
    if role_ids:
        roles = {
            role.job_role_id: (role.role_code, role.canonical_name)
            for role in db.scalars(select(JobRole).where(JobRole.job_role_id.in_(role_ids)))
        }
    return CandidatePage(
        total=total,
        items=[
            CandidateListItem(
                candidate_code=candidate.candidate_code,
                proposed_name=candidate.proposed_name,
                maturity_stage_code=candidate.maturity_stage_code,
                workflow_status_code=candidate.workflow_status_code,
                candidate_score=candidate.candidate_score,
                support_job_count=candidate.support_job_count,
                classification_code=candidate.classification_code,
                gap_grade=(candidate.mechanical_card_json or {}).get("gap_grade"),
                approved_role_code=roles.get(candidate.approved_job_role_id, (None, None))[0],
                approved_role_name=roles.get(candidate.approved_job_role_id, (None, None))[1],
                # 候选表没有独立的审批时间字段，入库是 updated_at 的最后一次写入。
                # 命名上说清它是「最后更新时间」而非严格的审批时刻。
                approved_at=(
                    candidate.updated_at.isoformat() if candidate.approved_job_role_id else None
                ),
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


@router.get("/role-discovery/unverified-technologies", response_model=dict)
def get_unverified_technologies(db: Annotated[Session, Depends(get_db)]):
    """C 级待核查技术清单：上游语料中活跃、而全部 JD 中一次都没出现的技术点。

    每条要回答的是同一个问题——该技术是市场尚未覆盖的新技术，还是根本不属于具身
    智能招聘范围？本系统区分不了，需要人工判断。按技术点聚合而非按技术对：
    96 对背后只有 23 个技术，判断一次即可复用到该技术涉及的所有对上。

    清单由 `build_upstream_candidates` 写进推演运行的结果摘要，这里直接读库——
    API 进程不去读语料文件。
    """
    run = db.scalar(
        select(DiscoveryRun)
        .where(
            DiscoveryRun.mode_code == "upstream_gap",
            DiscoveryRun.run_status_code == "success",
        )
        .order_by(DiscoveryRun.discovery_run_id.desc())
    )
    if run is None or not run.result_summary_json:
        return {"run_code": None, "items": [], "note": "尚未运行上游缺口推演"}
    summary = run.result_summary_json
    return {
        "run_code": run.run_code,
        "generated_at": run.completed_at.isoformat() if run.completed_at else None,
        "note": summary.get("unverified_note", ""),
        "items": summary.get("unverified_technologies", []),
    }


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


@router.post("/role-discovery/candidates/{candidate_code}/expression/auto", response_model=dict)
def auto_expression(
    candidate_code: str,
    db: Annotated[Session, Depends(get_db)],
    _reviewer: Annotated[AppUser, Depends(get_reviewer)],
):
    """一键生成表达层：LLM 可用时生成并校验，否则规则降级。"""
    try:
        candidate = auto_candidate_expression(db, candidate_code=candidate_code)
    except DiscoveryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return candidate_snapshot(db, candidate)
