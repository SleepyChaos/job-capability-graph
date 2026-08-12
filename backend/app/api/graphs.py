from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.graph.service import (
    GraphProjectionError,
    cluster_capability_graph,
    cluster_graph_list,
    heatmap_graph,
    relation_graph,
    relation_graph_neighbors,
)

router = APIRouter(tags=["capability-graphs"])


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
