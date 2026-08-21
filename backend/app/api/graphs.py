from collections import defaultdict
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.graph.models import TripleContradictionAssessment
from app.modules.graph.service import (
    GraphProjectionError,
    capability_to_cluster_ranking,
    cluster_capability_graph,
    cluster_graph_list,
    heatmap_graph,
    industry_chain_summary,
    org_tech_graph,
    relation_graph,
    relation_graph_neighbors,
)

router = APIRouter(tags=["capability-graphs"])


@router.get("/graphs/industry-chain/summary", response_model=dict)
def get_industry_chain_summary(db: Annotated[Session, Depends(get_db)]):
    return industry_chain_summary(db)


@router.get("/graphs/relations", response_model=dict)
def get_relation_graph(
    db: Annotated[Session, Depends(get_db)],
    # ``domain_code``/``level_code`` remain as compatibility aliases for
    # existing clients. The relation page uses the explicit split filters
    # below so role clusters are not implicitly narrowed by capability
    # criteria.
    domain_code: Literal["T1", "T2", "T3", "T4", "T5", "T6", "T7"] | None = None,
    level_code: Literal["L1", "L2", "L3"] = "L2",
    cluster_domain_code: Literal["T1", "T2", "T3", "T4", "T5", "T6", "T7"] | None = None,
    capability_domain_code: Literal["T1", "T2", "T3", "T4", "T5", "T6", "T7"] | None = None,
    capability_level_code: Literal["L1", "L2", "L3"] | None = None,
    cluster_limit: Annotated[int, Query(ge=1, le=1000)] = 1000,
    capabilities_per_cluster: Annotated[int, Query(ge=1, le=40)] = 20,
    node_budget: Annotated[int, Query(ge=2, le=1000)] = 240,
    min_supporting_job_count: Annotated[int, Query(ge=1, le=1000)] = 1,
    mode: Literal["overview", "focus"] = "overview",
    focus_node_id: str | None = None,
    industry_stage: Literal["upstream", "midstream", "downstream", "support", "unclassified"] | None = None,
):
    try:
        return relation_graph(
            db,
            # The explicit parameters take precedence. Legacy callers keep
            # the old capability-only behavior without breaking the route.
            cluster_domain_code=cluster_domain_code,
            capability_domain_code=(
                capability_domain_code if capability_domain_code is not None else domain_code
            ),
            capability_level_code=capability_level_code or level_code,
            cluster_limit=cluster_limit,
            capabilities_per_cluster=capabilities_per_cluster,
            node_budget=node_budget,
            min_supporting_job_count=min_supporting_job_count,
            mode=mode,
            focus_node_id=focus_node_id,
            industry_stage=industry_stage,
        )
    except GraphProjectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/graphs/relations/{node_id}/neighbors", response_model=dict)
def get_relation_graph_neighbors(
    node_id: str,
    db: Annotated[Session, Depends(get_db)],
    cluster_domain_code: Literal["T1", "T2", "T3", "T4", "T5", "T6", "T7"] | None = None,
    capability_domain_code: Literal["T1", "T2", "T3", "T4", "T5", "T6", "T7"] | None = None,
    capability_level_code: Literal["L1", "L2", "L3"] = "L2",
    min_supporting_job_count: Annotated[int, Query(ge=1, le=1000)] = 1,
    neighbor_limit: Annotated[int, Query(ge=1, le=160)] = 60,
):
    try:
        return relation_graph_neighbors(
            db,
            node_id=node_id,
            cluster_domain_code=cluster_domain_code,
            capability_domain_code=capability_domain_code,
            capability_level_code=capability_level_code,
            min_supporting_job_count=min_supporting_job_count,
            neighbor_limit=neighbor_limit,
        )
    except GraphProjectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/graphs/clusters", response_model=dict)
def get_graph_clusters(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
):
    try:
        return cluster_graph_list(db, limit=limit)
    except GraphProjectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/graphs/clusters/{stable_cluster_code}", response_model=dict)
def get_cluster_capability_graph(
    stable_cluster_code: str,
    db: Annotated[Session, Depends(get_db)],
    level_code: Literal["L1", "L2", "L3"] = "L2",
    capability_limit: Annotated[int, Query(ge=1, le=40)] = 20,
    recent_job_count: Annotated[int, Query(ge=3, le=50)] = 10,
):
    try:
        return cluster_capability_graph(
            db,
            stable_cluster_code=stable_cluster_code,
            level_code=level_code,
            capability_limit=capability_limit,
            recent_job_count=recent_job_count,
        )
    except GraphProjectionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/graphs/heatmap", response_model=dict)
def get_heatmap_graph(
    db: Annotated[Session, Depends(get_db)],
    domain_code: Literal["T1", "T2", "T3", "T4", "T5", "T6", "T7"] | None = None,
    level_code: Literal["L1", "L2", "L3"] = "L2",
):
    try:
        return heatmap_graph(db, domain_code=domain_code, level_code=level_code)
    except GraphProjectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/graphs/org-tech", response_model=dict)
def get_org_tech_graph(
    db: Annotated[Session, Depends(get_db)],
    capability_domain_code: Literal["T1", "T2", "T3", "T4", "T5", "T6", "T7"] | None = None,
    capability_level_code: Literal["L1", "L2", "L3"] = "L2",
    org_limit: Annotated[int, Query(ge=1, le=500)] = 40,
    capabilities_per_org: Annotated[int, Query(ge=1, le=100)] = 20,
    min_supporting_job_count: Annotated[int, Query(ge=1, le=1000)] = 1,
    industry_stage: Literal["upstream", "midstream", "downstream", "support", "unclassified"] | None = None,
):
    try:
        return org_tech_graph(
            db,
            capability_domain_code=capability_domain_code,
            capability_level_code=capability_level_code,
            org_limit=org_limit,
            capabilities_per_org=capabilities_per_org,
            min_supporting_job_count=min_supporting_job_count,
            industry_stage=industry_stage,
        )
    except GraphProjectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/graphs/capability-to-clusters", response_model=dict)
def get_capability_to_cluster_ranking(
    db: Annotated[Session, Depends(get_db)],
    capability_domain_code: Literal["T1", "T2", "T3", "T4", "T5", "T6", "T7"] | None = None,
    capability_level_code: Literal["L1", "L2", "L3"] = "L2",
    min_supporting_job_count: Annotated[int, Query(ge=1, le=1000)] = 1,
    limit: Annotated[int, Query(ge=1, le=2000)] = 300,
):
    try:
        return capability_to_cluster_ranking(
            db,
            capability_domain_code=capability_domain_code,
            capability_level_code=capability_level_code,
            min_supporting_job_count=min_supporting_job_count,
            limit=limit,
        )
    except GraphProjectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---------------- Layer C: 三元组矛盾打分 ----------------

class TripleAuditSummary(BaseModel):
    audit_run_code: str
    audit_model: str
    sample_scope: str
    total_triples: int
    low_plausibility: int
    medium_plausibility: int
    high_plausibility: int
    auto_suppressed: int = 0
    pending_review: int
    accepted_as_true: int
    false_positive_edge: int
    redirected_edge: int


class TripleAuditRow(BaseModel):
    triple_id: int
    subject_kind: str
    subject_id: str
    subject_label: str
    predicate: str
    object_kind: str
    object_id: str
    object_label: str
    plausibility_score: float
    plausibility_level: str
    review_status_code: str
    reviewer_code: str | None
    supporting_job_count: int
    component_scores: dict = Field(default_factory=dict)
    rule_flags: dict = Field(default_factory=dict)


@router.get("/graphs/triple-audit/latest", response_model=dict)
def get_latest_triple_audit_summary(
    db: Annotated[Session, Depends(get_db)],
    audit_run_code: str | None = None,
):
    """获取最近一次矛盾打分的审计总览 + 低分待复核列表 Top-N。"""
    if audit_run_code is None:
        latest = db.scalar(
            select(TripleContradictionAssessment.audit_run_code)
            .order_by(desc(TripleContradictionAssessment.created_at))
            .limit(1)
        )
        audit_run_code = latest
    if audit_run_code is None:
        return {
            "summary": None,
            "low_plausibility_rows": [],
            "hint": "还未运行矛盾打分。在 backend 容器执行 `python -m tools.layer_c_triple_audit --sample-scope top_200` 即可生成。",
        }
    rows = list(
        db.scalars(
            select(TripleContradictionAssessment).where(
                TripleContradictionAssessment.audit_run_code == audit_run_code
            )
        )
    )
    total = len(rows)
    low = sum(1 for r in rows if r.plausibility_level == "low")
    mid = sum(1 for r in rows if r.plausibility_level == "medium")
    high = sum(1 for r in rows if r.plausibility_level == "high")
    supp = sum(1 for r in rows if r.plausibility_level == "auto_suppressed")
    review_status: dict[str, int] = defaultdict(int)
    for r in rows:
        review_status[r.review_status_code] += 1
    summary = TripleAuditSummary(
        audit_run_code=audit_run_code,
        audit_model=rows[0].audit_model if rows else "composite_v1",
        sample_scope=rows[0].sample_scope if rows else "top_200",
        total_triples=total,
        low_plausibility=low,
        medium_plausibility=mid,
        high_plausibility=high,
        auto_suppressed=supp,
        pending_review=review_status.get("pending_review", 0),
        accepted_as_true=review_status.get("accepted_as_true", 0),
        false_positive_edge=review_status.get("false_positive_edge", 0),
        redirected_edge=review_status.get("redirected_edge", 0),
    )
    low_sorted = sorted(
        [r for r in rows if r.plausibility_level in {"low", "medium"}],
        key=lambda r: float(r.plausibility_score),
    )[:200]
    low_rows = [
        TripleAuditRow(
            triple_id=r.triple_contradiction_assessment_id,
            subject_kind=r.subject_kind,
            subject_id=r.subject_id,
            subject_label=r.subject_label,
            predicate=r.predicate,
            object_kind=r.object_kind,
            object_id=r.object_id,
            object_label=r.object_label,
            plausibility_score=float(r.plausibility_score),
            plausibility_level=r.plausibility_level,
            review_status_code=r.review_status_code,
            reviewer_code=r.reviewer_code,
            supporting_job_count=int((r.evidence_summary_json or {}).get("supporting_job_count", 0)),
            component_scores=r.component_scores or {},
            rule_flags=r.rule_flags or {},
        )
        for r in low_sorted
    ]
    return {
        "summary": summary.model_dump(),
        "low_plausibility_rows": [r.model_dump() for r in low_rows],
        "hint": "低分边请人工复核后更新 review_status_code。",
    }
