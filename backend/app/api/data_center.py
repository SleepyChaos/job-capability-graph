from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.data_center.models import (
    AppUser,
    CollectionRun,
    MilestoneEvent,
    ReviewTask,
    SourceCollectionPolicy,
)
from app.modules.data_center.service import (
    DataCenterError,
    MilestoneSubmission,
    create_collection_run,
    milestone_snapshot,
    record_collection_request,
    review_milestone,
    submit_milestone_candidate,
)
from app.modules.ingestion.web_crawler import run_web_collection
from app.modules.job.models import DataSource, SourceDocument, SourceDocumentVersion

router = APIRouter(tags=["data-center"])


class SourceCreate(BaseModel):
    source_code: str = Field(min_length=1, max_length=64)
    source_name: str = Field(min_length=1, max_length=300)
    source_type_code: Literal["recruitment", "enterprise", "government", "research", "other"]
    entry_url: str | None = Field(default=None, max_length=1500)
    content_type_code: Literal["job", "industry", "milestone", "mixed"] = "mixed"
    authority_level_code: str | None = None
    independent_source_group: str | None = None
    default_reliability_score: Decimal = Field(ge=0, le=100)


class SourceResponse(BaseModel):
    source_code: str
    source_name: str
    source_type_code: str
    entry_url: str | None
    content_type_code: str
    default_reliability_score: Decimal | None
    source_status_code: str


class PolicyCreate(BaseModel):
    source_code: str
    policy_version: str
    max_depth: int = Field(default=1, ge=0, le=1)
    schedule_cron: str | None = None
    timezone_name: str = "Asia/Shanghai"
    rate_limit_per_minute: int = Field(default=30, ge=1, le=600)
    domain_concurrency: int = Field(default=1, ge=1, le=10)
    robots_status_code: Literal["unchecked", "allowed", "restricted", "disallowed"] = "unchecked"
    terms_checked: bool = False
    allowed_scope_json: dict | None = None
    parser_code: str | None = None


class PolicyResponse(BaseModel):
    collection_policy_id: int
    source_code: str
    policy_version: str
    max_depth: int
    schedule_cron: str | None
    timezone_name: str
    rate_limit_per_minute: int
    domain_concurrency: int
    robots_status_code: str
    terms_checked: bool
    is_active: bool


class CollectionRunCreate(BaseModel):
    source_code: str
    policy_version: str
    scheduled_at: datetime | None = None


class CollectionRunResponse(BaseModel):
    run_code: str
    source_code: str
    policy_version: str
    run_status_code: str
    scheduled_at: datetime | None
    discovered_count: int
    changed_count: int
    unchanged_count: int
    failed_count: int
    error_summary: str | None = None


class CollectionRequestCreate(BaseModel):
    request_url: str = Field(min_length=1, max_length=1500)
    request_depth: int = Field(ge=0, le=1)
    request_type_code: Literal["entry", "list", "detail"]
    parent_request_id: int | None = None


class CollectionRequestResponse(BaseModel):
    collection_request_id: int
    run_code: str
    request_url: str
    request_depth: int
    request_type_code: str
    request_status_code: str
    parse_status_code: str


class MilestoneCandidateCreate(BaseModel):
    data_source_code: str
    source_record_key: str = Field(min_length=1, max_length=500)
    canonical_url: str = Field(min_length=1, max_length=1500)
    title: str = Field(min_length=1, max_length=1000)
    content_text: str = Field(min_length=1)
    published_at: datetime | None = None
    collected_at: datetime
    milestone_name: str = Field(min_length=1, max_length=500)
    milestone_type_code: str = Field(min_length=1, max_length=32)
    event_date: date | None = None
    event_year: int = Field(ge=1900, le=2200)
    description_text: str = Field(min_length=1)
    maturity_delta_score: Decimal | None = Field(default=None, ge=-100, le=100)
    evidence_quote: str = Field(min_length=1)
    technology_codes: list[str] = Field(min_length=1)


class MilestoneResponse(BaseModel):
    milestone_code: str
    milestone_name: str
    milestone_type_code: str
    event_date: date | None
    event_year: int
    description_text: str
    maturity_delta_score: Decimal | None
    verification_status_code: str
    technology_codes: list[str]


class MilestonePage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[MilestoneResponse]


class ReviewTaskResponse(BaseModel):
    task_code: str
    queue_code: str
    target_type_code: str
    target_id: int
    priority_score: Decimal
    task_status_code: str
    assigned_user_code: str | None
    target_snapshot: dict
    reason: dict | None


class ReviewActionRequest(BaseModel):
    action_code: Literal["claim", "approve", "reject", "needs_revision"]
    comment_text: str | None = None


def _error(exc: DataCenterError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _source_response(source: DataSource) -> SourceResponse:
    return SourceResponse(
        source_code=source.source_code,
        source_name=source.source_name,
        source_type_code=source.source_type_code,
        entry_url=source.entry_url,
        content_type_code=source.content_type_code,
        default_reliability_score=source.default_reliability_score,
        source_status_code=source.source_status_code,
    )


def _milestone_response(db: Session, milestone: MilestoneEvent) -> MilestoneResponse:
    snapshot = milestone_snapshot(db, milestone)
    return MilestoneResponse(**snapshot)


def get_reviewer(
    db: Annotated[Session, Depends(get_db)],
    reviewer_code: Annotated[str | None, Header(alias="X-Reviewer-Code")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> AppUser:
    """审核身份：优先 Bearer JWT，过渡期兼容 X-Reviewer-Code（Q8）。"""
    from app.api.auth import resolve_bearer_user

    bearer_user = resolve_bearer_user(db, authorization)
    if bearer_user is not None:
        if bearer_user.role_code not in {"reviewer", "admin"}:
            raise HTTPException(status_code=403, detail="当前账号没有审核权限")
        return bearer_user
    if not reviewer_code:
        raise HTTPException(
            status_code=401, detail="缺少认证：请提供 Bearer 令牌或开发期 X-Reviewer-Code 头"
        )
    user = db.scalar(
        select(AppUser).where(AppUser.user_code == reviewer_code, AppUser.is_active.is_(True))
    )
    if user is None or user.role_code not in {"reviewer", "admin"}:
        raise HTTPException(status_code=403, detail="审核身份无效或没有审核权限")
    return user


@router.post("/sources", response_model=SourceResponse, status_code=201)
def create_source(payload: SourceCreate, db: Annotated[Session, Depends(get_db)]):
    if db.scalar(select(DataSource).where(DataSource.source_code == payload.source_code)):
        raise HTTPException(status_code=409, detail="数据源编码已存在")
    source = DataSource(**payload.model_dump())
    db.add(source)
    db.commit()
    return _source_response(source)


@router.get("/sources", response_model=list[SourceResponse])
def list_sources(db: Annotated[Session, Depends(get_db)]):
    return [
        _source_response(item)
        for item in db.scalars(select(DataSource).order_by(DataSource.source_code))
    ]


@router.post("/collection-policies", response_model=PolicyResponse, status_code=201)
def create_policy(payload: PolicyCreate, db: Annotated[Session, Depends(get_db)]):
    source = db.scalar(select(DataSource).where(DataSource.source_code == payload.source_code))
    if source is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    if payload.robots_status_code in {"restricted", "disallowed"}:
        raise HTTPException(status_code=422, detail="当前 robots 状态不允许启用自动采集策略")
    policy = SourceCollectionPolicy(
        data_source_id=source.data_source_id,
        policy_version=payload.policy_version,
        max_depth=payload.max_depth,
        schedule_cron=payload.schedule_cron,
        timezone_name=payload.timezone_name,
        rate_limit_per_minute=payload.rate_limit_per_minute,
        domain_concurrency=payload.domain_concurrency,
        robots_status_code=payload.robots_status_code,
        terms_checked=payload.terms_checked,
        allowed_scope_json=payload.allowed_scope_json,
        parser_code=payload.parser_code,
    )
    db.add(policy)
    db.commit()
    return _policy_response(policy, source.source_code)


@router.get("/collection-policies", response_model=list[PolicyResponse])
def list_policies(db: Annotated[Session, Depends(get_db)]):
    rows = db.execute(
        select(SourceCollectionPolicy, DataSource.source_code)
        .join(DataSource, DataSource.data_source_id == SourceCollectionPolicy.data_source_id)
        .order_by(DataSource.source_code, SourceCollectionPolicy.policy_version)
    ).all()
    return [_policy_response(policy, code) for policy, code in rows]


def _policy_response(policy: SourceCollectionPolicy, source_code: str) -> PolicyResponse:
    return PolicyResponse(
        collection_policy_id=policy.collection_policy_id,
        source_code=source_code,
        policy_version=policy.policy_version,
        max_depth=policy.max_depth,
        schedule_cron=policy.schedule_cron,
        timezone_name=policy.timezone_name,
        rate_limit_per_minute=policy.rate_limit_per_minute,
        domain_concurrency=policy.domain_concurrency,
        robots_status_code=policy.robots_status_code,
        terms_checked=policy.terms_checked,
        is_active=policy.is_active,
    )


@router.post("/collection-runs", response_model=CollectionRunResponse, status_code=201)
def create_run(payload: CollectionRunCreate, db: Annotated[Session, Depends(get_db)]):
    row = db.execute(
        select(DataSource, SourceCollectionPolicy)
        .join(
            SourceCollectionPolicy,
            SourceCollectionPolicy.data_source_id == DataSource.data_source_id,
        )
        .where(
            DataSource.source_code == payload.source_code,
            SourceCollectionPolicy.policy_version == payload.policy_version,
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="数据源或采集策略不存在")
    try:
        run = create_collection_run(
            db, source=row[0], policy=row[1], scheduled_at=payload.scheduled_at
        )
    except DataCenterError as exc:
        raise _error(exc) from exc
    db.commit()
    return _run_response(run, payload.source_code, payload.policy_version)


@router.get("/collection-runs", response_model=list[CollectionRunResponse])
def list_runs(db: Annotated[Session, Depends(get_db)]):
    rows = db.execute(
        select(CollectionRun, DataSource.source_code, SourceCollectionPolicy.policy_version)
        .join(DataSource, DataSource.data_source_id == CollectionRun.data_source_id)
        .join(
            SourceCollectionPolicy,
            SourceCollectionPolicy.collection_policy_id == CollectionRun.collection_policy_id,
        )
        .order_by(CollectionRun.created_at.desc())
    ).all()
    return [_run_response(run, source_code, version) for run, source_code, version in rows]


def _run_response(
    run: CollectionRun, source_code: str, policy_version: str
) -> CollectionRunResponse:
    return CollectionRunResponse(
        run_code=run.run_code,
        source_code=source_code,
        policy_version=policy_version,
        run_status_code=run.run_status_code,
        scheduled_at=run.scheduled_at,
        discovered_count=run.discovered_count,
        changed_count=run.changed_count,
        unchanged_count=run.unchanged_count,
        failed_count=run.failed_count,
        error_summary=run.error_summary,
    )


@router.post(
    "/collection-runs/{run_code}/requests",
    response_model=CollectionRequestResponse,
    status_code=201,
)
def create_request(
    run_code: str, payload: CollectionRequestCreate, db: Annotated[Session, Depends(get_db)]
):
    run = db.scalar(select(CollectionRun).where(CollectionRun.run_code == run_code))
    if run is None:
        raise HTTPException(status_code=404, detail="采集运行不存在")
    try:
        request = record_collection_request(db, run=run, **payload.model_dump())
    except DataCenterError as exc:
        raise _error(exc) from exc
    db.commit()
    return CollectionRequestResponse(
        collection_request_id=request.collection_request_id,
        run_code=run.run_code,
        request_url=request.request_url,
        request_depth=request.request_depth,
        request_type_code=request.request_type_code,
        request_status_code=request.request_status_code,
        parse_status_code=request.parse_status_code,
    )


@router.post("/collection-runs/{run_code}/execute", response_model=CollectionRunResponse)
def execute_collection_run(run_code: str, db: Annotated[Session, Depends(get_db)]):
    """同步执行真实网页采集（P1 降级：无 Worker，请求内完成，见降级清单 D1）。"""
    run = db.scalar(select(CollectionRun).where(CollectionRun.run_code == run_code))
    if run is None:
        raise HTTPException(status_code=404, detail="采集运行不存在")
    if run.run_status_code not in {"pending", "failed"}:
        raise HTTPException(status_code=422, detail="该运行已执行或正在执行")
    source = db.get(DataSource, run.data_source_id)
    policy = db.get(SourceCollectionPolicy, run.collection_policy_id)
    if source is None or policy is None:
        raise HTTPException(status_code=404, detail="数据源或采集策略不存在")
    try:
        run_web_collection(db, run=run, source=source, policy=policy)
    except DataCenterError as exc:
        db.rollback()
        raise _error(exc) from exc
    except Exception as exc:  # noqa: BLE001 - 网络异常不应中断服务
        db.rollback()
        raise HTTPException(status_code=502, detail=f"采集执行失败：{exc}") from exc
    db.commit()
    return _run_response(run, source.source_code, policy.policy_version)


@router.post("/milestones/candidates", response_model=MilestoneResponse, status_code=201)
def create_milestone_candidate(
    payload: MilestoneCandidateCreate, db: Annotated[Session, Depends(get_db)]
):
    try:
        milestone = submit_milestone_candidate(
            db,
            MilestoneSubmission(
                **payload.model_dump(exclude={"technology_codes"}),
                technology_codes=tuple(payload.technology_codes),
            ),
        )
    except DataCenterError as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return _milestone_response(db, milestone)


@router.get("/milestones", response_model=MilestonePage)
def list_milestones(
    db: Annotated[Session, Depends(get_db)],
    status: str | None = None,
    search: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    filters = [MilestoneEvent.verification_status_code == status] if status else []
    if search:
        # 数据管理中心的搜索框对里程碑同样可用，此前后端无对应过滤，输入后没有任何反应。
        pattern = f"%{search}%"
        filters.append(
            MilestoneEvent.milestone_name.like(pattern)
            | MilestoneEvent.description_text.like(pattern)
        )
    total = db.scalar(select(func.count()).select_from(MilestoneEvent).where(*filters)) or 0
    milestones = list(
        db.scalars(
            select(MilestoneEvent)
            .where(*filters)
            .order_by(MilestoneEvent.event_year.desc(), MilestoneEvent.milestone_event_id)
            .offset(offset)
            .limit(limit)
        )
    )
    return MilestonePage(
        total=total,
        limit=limit,
        offset=offset,
        items=[_milestone_response(db, milestone) for milestone in milestones],
    )


@router.get("/milestones/{milestone_code}", response_model=MilestoneResponse)
def milestone_detail(milestone_code: str, db: Annotated[Session, Depends(get_db)]):
    milestone = db.scalar(
        select(MilestoneEvent).where(MilestoneEvent.milestone_code == milestone_code)
    )
    if milestone is None:
        raise HTTPException(status_code=404, detail="里程碑不存在")
    return _milestone_response(db, milestone)


@router.get("/reviews/data", response_model=list[ReviewTaskResponse])
def list_data_reviews(
    db: Annotated[Session, Depends(get_db)],
    status: str | None = None,
):
    filters = [ReviewTask.queue_code == "data_review"]
    if status:
        filters.append(ReviewTask.task_status_code == status)
    rows = db.execute(
        select(ReviewTask, AppUser.user_code)
        .outerjoin(AppUser, AppUser.user_id == ReviewTask.assigned_user_id)
        .where(*filters)
        .order_by(ReviewTask.priority_score.desc(), ReviewTask.created_at)
    ).all()
    return [
        ReviewTaskResponse(
            task_code=task.task_code,
            queue_code=task.queue_code,
            target_type_code=task.target_type_code,
            target_id=task.target_id,
            priority_score=task.priority_score,
            task_status_code=task.task_status_code,
            assigned_user_code=user_code,
            target_snapshot=task.target_snapshot_json,
            reason=task.reason_json,
        )
        for task, user_code in rows
    ]


@router.post("/reviews/data/{task_code}/actions", response_model=MilestoneResponse)
def act_on_data_review(
    task_code: str,
    payload: ReviewActionRequest,
    db: Annotated[Session, Depends(get_db)],
    reviewer: Annotated[AppUser, Depends(get_reviewer)],
):
    task = db.scalar(select(ReviewTask).where(ReviewTask.task_code == task_code))
    if task is None:
        raise HTTPException(status_code=404, detail="审核任务不存在")
    try:
        milestone = review_milestone(
            db,
            task=task,
            actor_user_id=reviewer.user_id,
            action_code=payload.action_code,
            comment_text=payload.comment_text,
        )
    except DataCenterError as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return _milestone_response(db, milestone)


# 原始文档检索。JD 与论文共用 raw_source_document，差别只在 document_type_code，
# 因此检索接口只有一套；数据管理中心的「原始文档」标签页与文献检索页读的是同一个端点。
class DocumentItem(BaseModel):
    document_code: str
    document_type_code: str
    title: str | None
    source_code: str
    source_name: str
    canonical_url: str | None
    source_record_key: str | None
    published_at: date | None
    excerpt: str
    categories: list[str]


class DocumentPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[DocumentItem]


class DocumentDetail(DocumentItem):
    content_text: str
    content_hash: str | None
    collected_at: datetime | None
    version_no: int


class DocumentFacetEntry(BaseModel):
    code: str
    label: str
    count: int


class DocumentFacets(BaseModel):
    total: int
    types: list[DocumentFacetEntry]
    sources: list[DocumentFacetEntry]
    years: list[DocumentFacetEntry]


DOCUMENT_TYPE_LABELS = {
    "job": "岗位 JD",
    "paper": "论文文献",
    "milestone_material": "里程碑材料",
}
EXCERPT_LENGTH = 240


def _document_filters(
    doc_type: str | None,
    source_code: str | None,
    year_from: int | None,
    year_to: int | None,
    search: str | None,
):
    filters = []
    if doc_type:
        filters.append(SourceDocument.document_type_code == doc_type)
    if source_code:
        filters.append(DataSource.source_code == source_code)
    if year_from is not None:
        filters.append(extract("year", SourceDocumentVersion.published_at) >= year_from)
    if year_to is not None:
        filters.append(extract("year", SourceDocumentVersion.published_at) <= year_to)
    if search:
        # 题名与正文都要能命中：论文按标题找，按摘要里的技术词找同样常见。
        pattern = f"%{search}%"
        filters.append(
            SourceDocument.title.like(pattern) | SourceDocumentVersion.content_text.like(pattern)
        )
    return filters


def _document_base():
    return (
        select(SourceDocument, SourceDocumentVersion, DataSource)
        .join(
            SourceDocumentVersion,
            (SourceDocumentVersion.source_document_id == SourceDocument.source_document_id)
            & (SourceDocumentVersion.is_current.is_(True)),
        )
        .join(DataSource, DataSource.data_source_id == SourceDocument.data_source_id)
    )


def _document_item(
    document: SourceDocument, version: SourceDocumentVersion, source: DataSource
) -> DocumentItem:
    payload = version.content_json if isinstance(version.content_json, dict) else {}
    text = version.content_text or ""
    return DocumentItem(
        document_code=document.document_code,
        document_type_code=document.document_type_code,
        title=document.title,
        source_code=source.source_code,
        source_name=source.source_name,
        canonical_url=document.canonical_url,
        source_record_key=document.source_record_key,
        published_at=version.published_at.date() if version.published_at else None,
        excerpt=text[:EXCERPT_LENGTH] + ("…" if len(text) > EXCERPT_LENGTH else ""),
        categories=[str(item) for item in (payload.get("categories") or [])],
    )


@router.get("/documents/facets", response_model=DocumentFacets)
def document_facets(db: Annotated[Session, Depends(get_db)]):
    base = _document_base().subquery()
    total = db.scalar(select(func.count()).select_from(base)) or 0
    types = [
        DocumentFacetEntry(
            code=code, label=DOCUMENT_TYPE_LABELS.get(code, code), count=int(count)
        )
        for code, count in db.execute(
            select(base.c.document_type_code, func.count())
            .group_by(base.c.document_type_code)
            .order_by(func.count().desc())
        ).all()
    ]
    sources = [
        DocumentFacetEntry(code=code, label=name, count=int(count))
        for code, name, count in db.execute(
            select(base.c.source_code, base.c.source_name, func.count())
            .group_by(base.c.source_code, base.c.source_name)
            .order_by(func.count().desc())
        ).all()
    ]
    years = [
        DocumentFacetEntry(code=str(int(year)), label=f"{int(year)} 年", count=int(count))
        for year, count in db.execute(
            select(extract("year", base.c.published_at), func.count())
            .where(base.c.published_at.is_not(None))
            .group_by(extract("year", base.c.published_at))
            .order_by(extract("year", base.c.published_at).desc())
        ).all()
    ]
    return DocumentFacets(total=total, types=types, sources=sources, years=years)


@router.get("/documents", response_model=DocumentPage)
def list_documents(
    db: Annotated[Session, Depends(get_db)],
    search: str | None = None,
    doc_type: str | None = None,
    source_code: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    filters = _document_filters(doc_type, source_code, year_from, year_to, search)
    total = db.scalar(
        select(func.count())
        .select_from(SourceDocument)
        .join(
            SourceDocumentVersion,
            (SourceDocumentVersion.source_document_id == SourceDocument.source_document_id)
            & (SourceDocumentVersion.is_current.is_(True)),
        )
        .join(DataSource, DataSource.data_source_id == SourceDocument.data_source_id)
        .where(*filters)
    ) or 0
    rows = db.execute(
        _document_base()
        .where(*filters)
        # 有发表日期的排前面：论文有干净的时间轴，JD 侧大量为空，按空值排在后面更可读。
        .order_by(
            SourceDocumentVersion.published_at.is_(None),
            SourceDocumentVersion.published_at.desc(),
            SourceDocument.source_document_id,
        )
        .offset(offset)
        .limit(limit)
    ).all()
    return DocumentPage(
        total=total,
        limit=limit,
        offset=offset,
        items=[_document_item(document, version, source) for document, version, source in rows],
    )


@router.get("/documents/{document_code}", response_model=DocumentDetail)
def document_detail(document_code: str, db: Annotated[Session, Depends(get_db)]):
    row = db.execute(
        _document_base().where(SourceDocument.document_code == document_code)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="原始文档不存在")
    document, version, source = row
    return DocumentDetail(
        **_document_item(document, version, source).model_dump(),
        content_text=version.content_text or "",
        content_hash=version.content_hash,
        collected_at=version.collected_at,
        version_no=version.version_no,
    )
