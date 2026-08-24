import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.modules.clustering.models import (
    JobClusteringRun,
    JobClusterMember,
    JobClusterVersion,
)
from app.modules.discovery.models import (
    CandidateTechnology,
    DiscoveryRun,
    EmergingRoleCandidate,
)
from app.modules.discovery.service import ALGORITHM_VERSION as DISCOVERY_ALGORITHM_VERSION
from app.modules.graph.models import (
    DOMAIN_AGGREGATE_TECHNOLOGY_ID,
    TechnologyDailyTriggerMetric,
)
from app.modules.job.models import (
    JobParseRun,
    JobPosting,
    JobRequirement,
    TechnologyMatchAssessment,
)
from app.modules.taxonomy.models import (
    TechnologyDomain,
    TechnologyNode,
    TechnologyNodeDomain,
)

PROJECTION_VERSION = "graph_projection_p2_v1"
DAILY_METRIC_CALCULATION_VERSION = "daily_trigger_metric_v1"
DOMAIN_LEDGER = {
    "T1": ("智能算法与模型", "#1769e0"),
    "T2": ("感知与传感", "#0b9c93"),
    "T3": ("本体与核心零部件", "#38a8dc"),
    "T4": ("数据与仿真", "#6fbd73"),
    "T5": ("系统软件与工具链", "#f2a43a"),
    "T6": ("交互、安全与评测标准", "#8e7ad5"),
    "T7": ("应用与场景", "#64748b"),
}


class GraphProjectionError(ValueError):
    """A user-correctable graph projection error."""


@dataclass(frozen=True)
class RequirementSignal:
    job_posting_id: int
    job_code: str
    technology_node_id: int
    mention_count: int
    organization_id: int | None
    data_source_id: int
    observed_at: datetime | None


@dataclass(frozen=True)
class ProjectionContext:
    run: JobClusteringRun
    parse_run: JobParseRun
    nodes: dict[int, TechnologyNode]
    primary_domains: dict[int, str]
    signals: tuple[RequirementSignal, ...]
    data_version: str


def _candidate_projection(
    db: Session,
    context: ProjectionContext,
    *,
    capability_level_code: str,
    capability_domain_code: str | None,
    capability_nodes: dict[int, dict],
    limit: int,
) -> tuple[list[dict], list[dict]]:
    """把新岗位候选投影成与岗位聚类同级的 role 节点。

    **候选与聚类同级。** 聚类是「从真实 JD 观测到的岗位归并」，候选是「算法提议的
    岗位」，两者都属于 role 一侧，连的是同一批能力节点。指标也一一对应：
    成员数 ↔ 支撑 JD 数、独立企业数 ↔ 独立企业数、簇内聚度 ↔ 候选评分。

    **必须按技术编码而非节点 id 关联。** 图谱的节点空间取自解析运行的词表版本，
    候选的技术 id 取自推演运行的词表版本，两者可能不同代。按 id 关联会得到空交集，
    候选看上去一条边都没有。技术编码跨版本稳定，是唯一可比的口径。

    候选的技术是 L3，图谱通常按 L2 呈现，因此沿父链上投到目标层级，与聚类能力
    指标走同一个 `_project_node`。
    """
    fresh_run_ids = set(
        db.scalars(
            select(DiscoveryRun.discovery_run_id).where(
                DiscoveryRun.algorithm_version == DISCOVERY_ALGORITHM_VERSION
            )
        )
    )
    if not fresh_run_ids:
        return [], []
    candidates = list(
        db.scalars(
            select(EmergingRoleCandidate)
            .where(EmergingRoleCandidate.last_seen_discovery_run_id.in_(fresh_run_ids))
            .order_by(EmergingRoleCandidate.candidate_score.desc())
            .limit(limit)
        )
    )
    if not candidates:
        return [], []

    node_by_code = {item.technology_code: item for item in context.nodes.values()}
    codes_by_candidate: dict[int, list[str]] = defaultdict(list)
    for candidate_id, code in db.execute(
        select(CandidateTechnology.emerging_role_candidate_id, TechnologyNode.technology_code)
        .join(
            TechnologyNode,
            TechnologyNode.technology_node_id == CandidateTechnology.technology_node_id,
        )
        .where(
            CandidateTechnology.emerging_role_candidate_id.in_(
                [item.emerging_role_candidate_id for item in candidates]
            ),
            CandidateTechnology.membership_code == "core",
        )
    ):
        codes_by_candidate[candidate_id].append(code)

    role_nodes: list[dict] = []
    edges: list[dict] = []
    for candidate in candidates:
        card = candidate.mechanical_card_json or {}
        targets: dict[int, TechnologyNode] = {}
        for code in codes_by_candidate.get(candidate.emerging_role_candidate_id, []):
            source = node_by_code.get(code)
            if source is None:
                # 该技术点在图谱所用的词表版本里已下线，跳过而不是连一条悬空边。
                continue
            projected = _project_node(
                context.nodes, source.technology_node_id, capability_level_code
            )
            if projected is not None:
                targets[projected.technology_node_id] = projected
        if not targets:
            continue

        domains = [context.primary_domains.get(item, "T7") for item in targets]
        primary_domain = Counter(domains).most_common(1)[0][0]
        if capability_domain_code and primary_domain != capability_domain_code:
            continue

        support = int(card.get("job_count", 0) or 0)
        role_nodes.append(
            {
                "id": f"candidate:{candidate.candidate_code}",
                "type": "emerging_candidate",
                "label": candidate.proposed_name,
                "domain_code": primary_domain,
                "metrics": {
                    "support_job_count": support,
                    "organization_count": int(card.get("organization_count", 0) or 0),
                    "candidate_score": _float(candidate.candidate_score),
                },
                # 提议尚未入库，前端据此区分呈现，并决定是否允许下钻到审核动作。
                "classification_code": candidate.classification_code,
                "maturity_stage_code": candidate.maturity_stage_code,
                "workflow_status_code": candidate.workflow_status_code,
                "evidence_count": support,
            }
        )
        for technology_id, technology in targets.items():
            if technology_id not in capability_nodes:
                # 能力节点没进本次预算，补一个零证据节点让边有落点。
                capability_nodes[technology_id] = {
                    "id": f"technology:{technology_id}",
                    "type": "technology",
                    "label": technology.technology_name,
                    "domain_code": context.primary_domains.get(technology_id, "T7"),
                    "level_code": technology.level_code,
                    "metrics": {"supporting_job_count": 0, "recent_activity": 0},
                    "evidence_count": 0,
                }
            edges.append(
                {
                    "id": f"edge:{candidate.candidate_code}:{technology_id}",
                    "source": f"candidate:{candidate.candidate_code}",
                    "target": f"technology:{technology_id}",
                    # 与聚类的 important_technology 区分：这是提议而非观测到的关联，
                    # 前端据此画虚线。
                    "relation_type": "proposed_technology",
                    "importance": _float(candidate.candidate_score),
                    "recent_activity": 0.0,
                    "supporting_job_count": support,
                    "coverage_rate": None,
                    "evidence_job_codes": [],
                }
            )
    return role_nodes, edges


def relation_graph(
    db: Session,
    *,
    cluster_domain_code: str | None = None,
    capability_domain_code: str | None = None,
    capability_level_code: str = "L2",
    cluster_limit: int = 1000,
    capabilities_per_cluster: int = 20,
    node_budget: int = 240,
    min_supporting_job_count: int = 1,
    mode: str = "overview",
    focus_node_id: str | None = None,
    # 新岗位候选默认不进图。它们是**未入库的提议**，与观测到的聚类混在一起会让
    # 读者分不清哪些是既有事实；由调用方显式打开，前端以虚线边和独立图例区分。
    include_candidates: bool = False,
    candidate_limit: int = 80,
    # Compatibility aliases for scripts and callers written before the
    # relation graph gained independent role/capability filters.
    domain_code: str | None = None,
    level_code: str | None = None,
) -> dict:
    if capability_domain_code is None:
        capability_domain_code = domain_code
    if level_code is not None and capability_level_code == "L2":
        capability_level_code = level_code
    if mode not in {"overview", "focus"}:
        raise GraphProjectionError("图谱模式仅支持 overview 或 focus")
    if mode == "focus" and not focus_node_id:
        raise GraphProjectionError("聚焦图谱需要提供 focus_node_id")
    if node_budget < 2:
        raise GraphProjectionError("节点预算至少为 2")
    if min_supporting_job_count < 1:
        raise GraphProjectionError("最小支持岗位数至少为 1")

    context = _context(db)
    _validate_filters(cluster_domain_code, capability_level_code)
    _validate_filters(capability_domain_code, capability_level_code)
    clusters = _active_clusters(db, context.run.clustering_run_id)
    if focus_node_id:
        focus_code = focus_node_id.removeprefix("cluster:")
        clusters = [item for item in clusters if item.stable_cluster_code == focus_code]
        if not clusters:
            raise GraphProjectionError("未找到指定的岗位聚类节点")
    if mode == "focus":
        cluster_limit = 1
    # Include every active role cluster that fits the overall node budget.
    # Capability nodes are de-duplicated below and consume the remaining
    # budget, so the default 720-node overview can hold the current full
    # cluster snapshot plus all evidence-backed L2 capabilities.
    effective_cluster_limit = min(cluster_limit, node_budget)
    memberships = _cluster_memberships(db, [item.job_cluster_version_id for item in clusters])
    signal_by_job = _signals_by_job(context.signals)
    projected = []
    for cluster in clusters:
        # The cluster domain is derived from its unfiltered L2 capability
        # profile. This keeps the role-cluster selector stable when the user
        # changes the capability level or capability domain selector.
        role_metrics = _cluster_capability_metrics(
            context,
            cluster,
            memberships.get(cluster.job_cluster_version_id, set()),
            signal_by_job,
            level_code="L2",
            recent_job_count=10,
        )
        role_domain = _primary_domain(role_metrics)
        if cluster_domain_code and role_domain != cluster_domain_code:
            continue

        capability_metrics = (
            role_metrics
            if capability_level_code == "L2"
            else _cluster_capability_metrics(
                context,
                cluster,
                memberships.get(cluster.job_cluster_version_id, set()),
                signal_by_job,
                level_code=capability_level_code,
                recent_job_count=10,
            )
        )
        if capability_domain_code:
            capability_metrics = [
                item
                for item in capability_metrics
                if item["domain_code"] == capability_domain_code
            ]
        capability_metrics = [
            item
            for item in capability_metrics
            if item["supporting_job_count"] >= min_supporting_job_count
        ]
        projected.append((cluster, role_domain, capability_metrics[:capabilities_per_cluster]))
        if len(projected) >= effective_cluster_limit:
            break

    capability_nodes = {}
    role_nodes = []
    edges = []
    capability_budget = max(0, node_budget - len(projected))
    for cluster, primary_domain, metrics in projected:
        role_nodes.append(
            {
                "id": f"cluster:{cluster.stable_cluster_code}",
                "type": "job_cluster",
                "label": cluster.cluster_label,
                "domain_code": primary_domain,
                "metrics": {
                    "member_count": cluster.member_count,
                    "organization_count": cluster.independent_organization_count,
                    "coherence_score": _float(cluster.coherence_score),
                },
                "evidence_count": cluster.member_count,
            }
        )
        for metric in metrics:
            technology_id = metric["technology_node_id"]
            if technology_id not in capability_nodes and len(capability_nodes) >= capability_budget:
                continue
            capability_node = capability_nodes.get(technology_id)
            if capability_node is None:
                capability_node = {
                    "id": f"technology:{technology_id}",
                    "type": "technology",
                    "label": metric["technology_name"],
                    "domain_code": metric["domain_code"],
                    "level_code": metric["level_code"],
                    "metrics": {
                        "supporting_job_count": 0,
                        "recent_activity": 0,
                    },
                    "evidence_count": 0,
                }
                capability_nodes[technology_id] = capability_node
            capability_node["metrics"]["supporting_job_count"] += metric[
                "supporting_job_count"
            ]
            capability_node["metrics"]["recent_activity"] = max(
                capability_node["metrics"]["recent_activity"], metric["recent_activity"]
            )
            capability_node["evidence_count"] += metric["supporting_job_count"]
            edges.append(
                {
                    "id": f"edge:{cluster.stable_cluster_code}:{technology_id}",
                    "source": f"cluster:{cluster.stable_cluster_code}",
                    "target": f"technology:{technology_id}",
                    "relation_type": "important_technology",
                    "importance": metric["importance"],
                    "recent_activity": metric["recent_activity"],
                    "supporting_job_count": metric["supporting_job_count"],
                    "coverage_rate": metric["coverage_rate"],
                    "evidence_job_codes": metric["evidence_job_codes"],
                }
            )

    # Keep the taxonomy visible even when an L2 capability has no accepted JD
    # relation in the current snapshot. Relation thresholds filter edges; they
    # do not erase governed capability nodes from the global overview.
    for technology in sorted(context.nodes.values(), key=lambda item: item.technology_code):
        if technology.level_code != capability_level_code:
            continue
        technology_id = technology.technology_node_id
        domain_code = context.primary_domains.get(technology_id, "T7")
        if capability_domain_code and domain_code != capability_domain_code:
            continue
        if technology_id in capability_nodes:
            continue
        if len(capability_nodes) >= capability_budget:
            break
        capability_nodes[technology_id] = {
            "id": f"technology:{technology_id}",
            "type": "technology",
            "label": technology.technology_name,
            "domain_code": domain_code,
            "level_code": technology.level_code,
            "metrics": {"supporting_job_count": 0, "recent_activity": 0},
            "evidence_count": 0,
        }
    candidate_nodes: list[dict] = []
    if include_candidates:
        candidate_nodes, candidate_edges = _candidate_projection(
            db,
            context,
            capability_level_code=capability_level_code,
            capability_domain_code=capability_domain_code,
            capability_nodes=capability_nodes,
            limit=candidate_limit,
        )
        role_nodes.extend(candidate_nodes)
        edges.extend(candidate_edges)

    return {
        **_metadata(context),
        "filters": {
            "include_candidates": include_candidates,
            "candidate_node_count": len(candidate_nodes),
            "cluster_domain_code": cluster_domain_code,
            "capability_domain_code": capability_domain_code,
            "capability_level_code": capability_level_code,
            "cluster_limit": effective_cluster_limit,
            "capabilities_per_cluster": capabilities_per_cluster,
            "node_budget": node_budget,
            "min_supporting_job_count": min_supporting_job_count,
            "mode": mode,
            "focus_node_id": focus_node_id,
        },
        "legend": _legend(),
        "role_nodes": role_nodes,
        "capability_nodes": list(capability_nodes.values()),
        "edges": edges,
        "rendering": {
            "artifact_family": "node_link",
            "primary_route": "canvas_force",
            "fallback": "edge_table",
            "layout_owner": "frontend_g6_force_worker",
            "semantic_zoom": True,
            "neighbor_expansion": True,
        },
    }


def relation_graph_neighbors(
    db: Session,
    *,
    node_id: str,
    cluster_domain_code: str | None = None,
    capability_domain_code: str | None = None,
    capability_level_code: str = "L2",
    min_supporting_job_count: int = 1,
    neighbor_limit: int = 60,
) -> dict:
    """Project just one node's immediate, governed neighbors.

    This endpoint deliberately does not reuse the overview node budget. The
    client can keep a compact overview and append bounded local neighborhoods
    as the user explores, rather than requesting a potentially thousand-node
    projection in one response.
    """
    if not node_id.startswith(("cluster:", "technology:")):
        raise GraphProjectionError("节点 ID 必须以 cluster: 或 technology: 开头")
    if min_supporting_job_count < 1:
        raise GraphProjectionError("最小支持岗位数至少为 1")
    if neighbor_limit < 1:
        raise GraphProjectionError("邻居上限至少为 1")

    context = _context(db)
    _validate_filters(cluster_domain_code, capability_level_code)
    _validate_filters(capability_domain_code, capability_level_code)
    clusters = _active_clusters(db, context.run.clustering_run_id)
    memberships = _cluster_memberships(db, [item.job_cluster_version_id for item in clusters])
    signal_by_job = _signals_by_job(context.signals)

    def role_metrics(cluster: JobClusterVersion) -> list[dict]:
        return _cluster_capability_metrics(
            context,
            cluster,
            memberships.get(cluster.job_cluster_version_id, set()),
            signal_by_job,
            level_code="L2",
            recent_job_count=10,
        )

    def capability_metrics(cluster: JobClusterVersion) -> list[dict]:
        metrics = _cluster_capability_metrics(
            context,
            cluster,
            memberships.get(cluster.job_cluster_version_id, set()),
            signal_by_job,
            level_code=capability_level_code,
            recent_job_count=10,
        )
        return [
            item
            for item in metrics
            if item["supporting_job_count"] >= min_supporting_job_count
            and (not capability_domain_code or item["domain_code"] == capability_domain_code)
        ]

    role_nodes: list[dict] = []
    capability_nodes: dict[int, dict] = {}
    edges: list[dict] = []

    def append_relation(cluster: JobClusterVersion, primary_domain: str, metric: dict) -> None:
        role_id = f"cluster:{cluster.stable_cluster_code}"
        technology_id = metric["technology_node_id"]
        if not any(item["id"] == role_id for item in role_nodes):
            role_nodes.append(
                {
                    "id": role_id,
                    "type": "job_cluster",
                    "label": cluster.cluster_label,
                    "domain_code": primary_domain,
                    "metrics": {
                        "member_count": cluster.member_count,
                        "organization_count": cluster.independent_organization_count,
                        "coherence_score": _float(cluster.coherence_score),
                    },
                    "evidence_count": cluster.member_count,
                }
            )
        capability_nodes[technology_id] = {
            "id": f"technology:{technology_id}",
            "type": "technology",
            "label": metric["technology_name"],
            "domain_code": metric["domain_code"],
            "level_code": metric["level_code"],
            "metrics": {
                "supporting_job_count": metric["supporting_job_count"],
                "recent_activity": metric["recent_activity"],
            },
            "evidence_count": metric["supporting_job_count"],
        }
        edges.append(
            {
                "id": f"edge:{cluster.stable_cluster_code}:{technology_id}",
                "source": role_id,
                "target": f"technology:{technology_id}",
                "relation_type": "important_technology",
                "importance": metric["importance"],
                "recent_activity": metric["recent_activity"],
                "supporting_job_count": metric["supporting_job_count"],
                "coverage_rate": metric["coverage_rate"],
                "evidence_job_codes": metric["evidence_job_codes"],
            }
        )

    if node_id.startswith("cluster:"):
        cluster_code = node_id.removeprefix("cluster:")
        cluster = next(
            (item for item in clusters if item.stable_cluster_code == cluster_code), None
        )
        if cluster is None:
            raise GraphProjectionError("未找到指定的岗位聚类节点")
        primary_domain = _primary_domain(role_metrics(cluster))
        if cluster_domain_code and primary_domain != cluster_domain_code:
            raise GraphProjectionError("指定岗位聚类不满足当前领域筛选")
        for metric in capability_metrics(cluster)[:neighbor_limit]:
            append_relation(cluster, primary_domain, metric)
    else:
        try:
            technology_id = int(node_id.removeprefix("technology:"))
        except ValueError as exc:
            raise GraphProjectionError("技术能力节点 ID 无效") from exc
        matches: list[tuple[JobClusterVersion, str, dict]] = []
        for cluster in clusters:
            primary_domain = _primary_domain(role_metrics(cluster))
            if cluster_domain_code and primary_domain != cluster_domain_code:
                continue
            metric = next(
                (
                    item
                    for item in capability_metrics(cluster)
                    if item["technology_node_id"] == technology_id
                ),
                None,
            )
            if metric:
                matches.append((cluster, primary_domain, metric))
        matches.sort(
            key=lambda item: (
                -item[2]["importance"],
                -item[2]["supporting_job_count"],
                item[0].stable_cluster_code,
            )
        )
        if not matches:
            raise GraphProjectionError("当前筛选下未找到该技术能力节点的关联岗位聚类")
        for cluster, primary_domain, metric in matches[:neighbor_limit]:
            append_relation(cluster, primary_domain, metric)

    return {
        **_metadata(context),
        "filters": {
            "cluster_domain_code": cluster_domain_code,
            "capability_domain_code": capability_domain_code,
            "capability_level_code": capability_level_code,
            "min_supporting_job_count": min_supporting_job_count,
            "neighbor_limit": neighbor_limit,
        },
        "legend": _legend(),
        "role_nodes": role_nodes,
        "capability_nodes": list(capability_nodes.values()),
        "edges": edges,
        "expansion": {
            "source_node_id": node_id,
            "returned_neighbor_count": len(role_nodes) + len(capability_nodes) - 1,
            "neighbor_limit": neighbor_limit,
            "truncated": len(edges) >= neighbor_limit,
        },
        "rendering": {
            "artifact_family": "node_link",
            "primary_route": "canvas_force",
            "fallback": "edge_table",
            "layout_owner": "frontend_g6_force_worker",
            "semantic_zoom": True,
            "neighbor_expansion": True,
        },
    }


def cluster_graph_list(db: Session, *, limit: int = 30) -> dict:
    context = _context(db)
    all_clusters = _active_clusters(db, context.run.clustering_run_id)
    clusters = all_clusters[:limit]
    memberships = _cluster_memberships(db, [item.job_cluster_version_id for item in clusters])
    signal_by_job = _signals_by_job(context.signals)
    items = []
    for cluster in clusters:
        metrics = _cluster_capability_metrics(
            context,
            cluster,
            memberships.get(cluster.job_cluster_version_id, set()),
            signal_by_job,
            level_code="L2",
            recent_job_count=10,
        )
        items.append(
            {
                "stable_cluster_code": cluster.stable_cluster_code,
                "label": cluster.cluster_label,
                "domain_code": _primary_domain(metrics),
                "member_count": cluster.member_count,
                "organization_count": cluster.independent_organization_count,
                "capability_count": len(metrics),
                "coherence_score": _float(cluster.coherence_score),
            }
        )
    return {
        **_metadata(context),
        "legend": _legend(),
        "total_active_cluster_count": len(all_clusters),
        "items": items,
    }


def cluster_capability_graph(
    db: Session,
    *,
    stable_cluster_code: str,
    level_code: str = "L2",
    capability_limit: int = 20,
    recent_job_count: int = 10,
) -> dict:
    context = _context(db)
    _validate_filters(None, level_code)
    cluster = db.scalar(
        select(JobClusterVersion).where(
            JobClusterVersion.clustering_run_id == context.run.clustering_run_id,
            JobClusterVersion.stable_cluster_code == stable_cluster_code,
            JobClusterVersion.cluster_status_code == "active",
        )
    )
    if cluster is None:
        raise GraphProjectionError("当前聚类快照中不存在该有效岗位聚类")
    members = _cluster_memberships(db, [cluster.job_cluster_version_id]).get(
        cluster.job_cluster_version_id, set()
    )
    metrics = _cluster_capability_metrics(
        context,
        cluster,
        members,
        _signals_by_job(context.signals),
        level_code=level_code,
        recent_job_count=recent_job_count,
    )[:capability_limit]
    return {
        **_metadata(context),
        "legend": _legend(),
        "cluster": {
            "stable_cluster_code": cluster.stable_cluster_code,
            "label": cluster.cluster_label,
            "description": cluster.cluster_description,
            "domain_code": _primary_domain(metrics),
            "member_count": cluster.member_count,
            "organization_count": cluster.independent_organization_count,
            "coherence_score": _float(cluster.coherence_score),
        },
        "capabilities": metrics,
        "encoding": {
            "distance": "inverse_normalized_long_term_importance",
            "hue": "primary_T_domain",
            "color_intensity": "recent_activity",
            "recent_basis": f"latest_{recent_job_count}_jobs_by_reliable_time_then_sequence",
        },
    }


def heatmap_graph(
    db: Session,
    *,
    domain_code: str | None = None,
    level_code: str = "L2",
    days: int = 45,
) -> dict:
    context = _context(db)
    _validate_filters(domain_code, level_code)
    if days != 45:
        raise GraphProjectionError("P0热力图固定使用45天窗口")
    aggregates = _heatmap_aggregates(context, level_code=level_code, days=days)
    dates = aggregates["dates"]
    domain_jobs = aggregates["domain_jobs"]
    domain_mentions = aggregates["domain_mentions"]
    technology_jobs = aggregates["technology_jobs"]
    technology_mentions = aggregates["technology_mentions"]
    technology_nodes = aggregates["technology_nodes"]
    observed_dates = aggregates["observed_dates"]
    # 设计 §11.4：L2 口径的按日触发指标同步落库，供离线复核与回放。
    metric_source = "runtime_projection"
    if level_code == "L2":
        _persist_daily_metrics(db, context, aggregates)
        db.commit()
        metric_source = "stored_daily_metric"

    domain_series = []
    global_rows = []
    for domain, (name, color) in DOMAIN_LEDGER.items():
        values = [
            _heat_cell(
                metric_date,
                domain_jobs[(domain, metric_date)],
                domain_mentions[(domain, metric_date)],
            )
            for metric_date in dates
        ]
        domain_series.append(
            {
                "domain_code": domain,
                "domain_name": name,
                "color": color,
                "total_trigger_documents": sum(item["trigger_document_count"] for item in values),
                "values": values,
            }
        )
        for band in range(3):
            global_rows.append(
                {
                    "row_index": len(global_rows),
                    "domain_code": domain,
                    "band_index": band,
                    "cells": values[band * 15 : (band + 1) * 15],
                }
            )

    detail_series = []
    if domain_code:
        for technology_id, (node, domain) in sorted(
            technology_nodes.items(), key=lambda item: item[1][0].technology_name
        ):
            if domain != domain_code:
                continue
            values = [
                _heat_cell(
                    metric_date,
                    technology_jobs[(technology_id, metric_date)],
                    technology_mentions[(technology_id, metric_date)],
                )
                for metric_date in dates
            ]
            detail_series.append(
                {
                    "technology_node_id": technology_id,
                    "technology_code": node.technology_code,
                    "technology_name": node.technology_name,
                    "level_code": node.level_code,
                    "domain_code": domain,
                    "total_trigger_documents": sum(
                        item["trigger_document_count"] for item in values
                    ),
                    "values": values,
                    "rows": [values[index : index + 15] for index in range(0, 45, 15)],
                }
            )
        detail_series.sort(
            key=lambda item: (-item["total_trigger_documents"], item["technology_code"])
        )

    coverage_ratio = len(observed_dates) / days
    return {
        **_metadata(context),
        "legend": _legend(),
        "window": {
            "start_date": dates[0].isoformat(),
            "end_date": dates[-1].isoformat(),
            "days": days,
            "observed_date_count": len(observed_dates),
            "coverage_ratio": _round(coverage_ratio, 4),
            "data_status": "complete" if coverage_ratio >= 0.8 else "partial",
            "warning": (
                None
                if coverage_ratio >= 0.8
                else "可靠源时间覆盖不足，零值可能表示未采集而非没有技术触发。"
            ),
        },
        "filters": {"domain_code": domain_code, "level_code": level_code},
        "metric_source": metric_source,
        "domain_series": domain_series,
        "global_rows": global_rows,
        "detail_series": detail_series,
        "rendering": {
            "artifact_family": "calendar_matrix",
            "global_shape": "21x15",
            "detail_shape": "3x15_per_technology",
            "default_metric": "trigger_document_count",
            "fallback": "daily_value_table",
        },
    }


def _context(db: Session) -> ProjectionContext:
    run = db.scalar(
        select(JobClusteringRun)
        .where(JobClusteringRun.run_status_code == "success")
        .order_by(JobClusteringRun.target_date.desc(), JobClusteringRun.clustering_run_id.desc())
    )
    if run is None:
        raise GraphProjectionError("不存在成功的岗位聚类运行")
    parse_run = db.get(JobParseRun, run.job_parse_run_id)
    if parse_run is None:
        raise GraphProjectionError("聚类运行缺少对应的JD解析运行")
    nodes = {
        item.technology_node_id: item
        for item in db.scalars(
            select(TechnologyNode).where(
                TechnologyNode.taxonomy_version_id == parse_run.taxonomy_version_id,
                TechnologyNode.governance_status_code == "active",
            )
        )
    }
    domains = {
        technology_id: domain_code
        for technology_id, domain_code in db.execute(
            select(TechnologyNodeDomain.technology_node_id, TechnologyDomain.domain_code)
            .join(
                TechnologyDomain,
                TechnologyDomain.technology_domain_id == TechnologyNodeDomain.technology_domain_id,
            )
            .where(
                TechnologyNodeDomain.technology_node_id.in_(list(nodes) or [-1]),
                TechnologyNodeDomain.is_primary.is_(True),
                TechnologyDomain.is_active.is_(True),
            )
        )
    }
    rows = db.execute(
        select(
            JobRequirement.job_posting_id,
            JobPosting.job_code,
            JobRequirement.technology_node_id,
            JobRequirement.mention_count,
            JobPosting.organization_id,
            JobPosting.data_source_id,
            JobPosting.source_collected_at,
            JobPosting.published_at,
        )
        .join(JobPosting, JobPosting.job_posting_id == JobRequirement.job_posting_id)
        .join(
            TechnologyMatchAssessment,
            TechnologyMatchAssessment.job_requirement_id == JobRequirement.job_requirement_id,
        )
        .where(
            TechnologyMatchAssessment.job_parse_run_id == parse_run.job_parse_run_id,
            TechnologyMatchAssessment.assessment_status_code == "accepted",
            JobRequirement.technology_node_id.is_not(None),
        )
        .distinct()
    ).all()
    signals = tuple(
        RequirementSignal(
            job_posting_id=job_id,
            job_code=job_code,
            technology_node_id=technology_id,
            mention_count=mention_count,
            organization_id=organization_id,
            data_source_id=data_source_id,
            observed_at=source_collected_at or published_at,
        )
        for (
            job_id,
            job_code,
            technology_id,
            mention_count,
            organization_id,
            data_source_id,
            source_collected_at,
            published_at,
        ) in rows
    )
    version_payload = (
        f"{PROJECTION_VERSION}|{run.run_code}|{run.input_snapshot_hash}|"
        f"{parse_run.input_snapshot_hash}|{len(signals)}"
    )
    return ProjectionContext(
        run=run,
        parse_run=parse_run,
        nodes=nodes,
        primary_domains=domains,
        signals=signals,
        data_version=hashlib.sha256(version_payload.encode()).hexdigest()[:24],
    )


def _active_clusters(db: Session, run_id: int) -> list[JobClusterVersion]:
    return list(
        db.scalars(
            select(JobClusterVersion)
            .where(
                JobClusterVersion.clustering_run_id == run_id,
                JobClusterVersion.cluster_status_code == "active",
            )
            .order_by(JobClusterVersion.member_count.desc(), JobClusterVersion.cluster_label)
        )
    )


def _cluster_memberships(db: Session, cluster_ids: list[int]) -> dict[int, set[int]]:
    result = defaultdict(set)
    for cluster_id, job_id in db.execute(
        select(JobClusterMember.job_cluster_version_id, JobClusterMember.job_posting_id).where(
            JobClusterMember.job_cluster_version_id.in_(cluster_ids or [-1])
        )
    ):
        result[cluster_id].add(job_id)
    return result


def _signals_by_job(
    signals: tuple[RequirementSignal, ...],
) -> dict[int, list[RequirementSignal]]:
    result = defaultdict(list)
    for signal in signals:
        result[signal.job_posting_id].append(signal)
    return result


def _cluster_capability_metrics(
    context: ProjectionContext,
    cluster: JobClusterVersion,
    member_ids: set[int],
    signal_by_job: dict[int, list[RequirementSignal]],
    *,
    level_code: str,
    recent_job_count: int,
) -> list[dict]:
    job_technology = defaultdict(set)
    mentions = Counter()
    evidence_codes = defaultdict(list)
    observed_at = {}
    for job_id in member_ids:
        for signal in signal_by_job.get(job_id, []):
            projected = _project_node(context.nodes, signal.technology_node_id, level_code)
            if projected is None:
                continue
            technology_id = projected.technology_node_id
            job_technology[technology_id].add(job_id)
            mentions[technology_id] += signal.mention_count
            if signal.job_code not in evidence_codes[technology_id]:
                evidence_codes[technology_id].append(signal.job_code)
            observed_at[job_id] = max(
                filter(None, [observed_at.get(job_id), signal.observed_at]),
                default=None,
            )
    recent_jobs = sorted(
        member_ids,
        key=lambda job_id: (observed_at.get(job_id) or datetime.min, job_id),
        reverse=True,
    )[:recent_job_count]
    max_support = max((len(items) for items in job_technology.values()), default=1)
    metrics = []
    for technology_id, support_jobs in job_technology.items():
        node = context.nodes[technology_id]
        recent_support = len(support_jobs & set(recent_jobs))
        coverage = len(support_jobs) / max(1, len(member_ids))
        importance = len(support_jobs) / max_support
        recent_activity = recent_support / max(1, len(recent_jobs))
        domain = context.primary_domains.get(technology_id)
        if domain not in DOMAIN_LEDGER:
            descendant_domains = [
                context.primary_domains.get(signal.technology_node_id)
                for job_id in support_jobs
                for signal in signal_by_job.get(job_id, [])
                if _project_node(context.nodes, signal.technology_node_id, level_code) == node
            ]
            domain = Counter(item for item in descendant_domains if item).most_common(1)
            domain = domain[0][0] if domain else "T7"
        last_seen = max(
            (observed_at.get(job_id) for job_id in support_jobs if observed_at.get(job_id)),
            default=None,
        )
        metrics.append(
            {
                "technology_node_id": technology_id,
                "technology_code": node.technology_code,
                "technology_name": node.technology_name,
                "level_code": node.level_code,
                "domain_code": domain,
                "importance": _round(importance * 100, 2),
                "recent_activity": _round(recent_activity * 100, 2),
                "supporting_job_count": len(support_jobs),
                "mention_count": mentions[technology_id],
                "coverage_rate": _round(coverage, 6),
                "last_seen_at": last_seen.isoformat() if last_seen else None,
                "evidence_job_codes": evidence_codes[technology_id][:10],
            }
        )
    return sorted(
        metrics,
        key=lambda item: (-item["importance"], -item["recent_activity"], item["technology_code"]),
    )


def _project_node(
    nodes: dict[int, TechnologyNode], technology_id: int, target_level: str
) -> TechnologyNode | None:
    node = nodes.get(technology_id)
    visited = set()
    while node and node.technology_node_id not in visited:
        if node.level_code == target_level:
            return node
        visited.add(node.technology_node_id)
        if node.parent_technology_node_id is None:
            return None
        node = nodes.get(node.parent_technology_node_id)
    return None


def _primary_domain(metrics: list[dict]) -> str:
    scores = Counter()
    for item in metrics:
        scores[item["domain_code"]] += item["supporting_job_count"]
    return scores.most_common(1)[0][0] if scores else "T7"


def _heatmap_aggregates(context: ProjectionContext, *, level_code: str, days: int) -> dict:
    """聚合 45 天窗口内的技术触发信号，同时记录独立企业与独立来源。"""
    dates = [context.run.target_date - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
    date_set = set(dates)
    domain_jobs = defaultdict(set)
    domain_mentions = Counter()
    domain_orgs = defaultdict(set)
    domain_sources = defaultdict(set)
    technology_jobs = defaultdict(set)
    technology_mentions = Counter()
    technology_orgs = defaultdict(set)
    technology_sources = defaultdict(set)
    technology_nodes = {}
    observed_dates = set()
    for signal in context.signals:
        if signal.observed_at is None:
            continue
        observed_date = signal.observed_at.date()
        if observed_date not in date_set:
            continue
        projected = _project_node(context.nodes, signal.technology_node_id, level_code)
        if projected is None:
            continue
        domain = context.primary_domains.get(
            projected.technology_node_id
        ) or context.primary_domains.get(signal.technology_node_id)
        if domain not in DOMAIN_LEDGER:
            continue
        observed_dates.add(observed_date)
        domain_jobs[(domain, observed_date)].add(signal.job_posting_id)
        domain_mentions[(domain, observed_date)] += signal.mention_count
        if signal.organization_id is not None:
            domain_orgs[(domain, observed_date)].add(signal.organization_id)
        domain_sources[(domain, observed_date)].add(signal.data_source_id)
        technology_jobs[(projected.technology_node_id, observed_date)].add(signal.job_posting_id)
        technology_mentions[(projected.technology_node_id, observed_date)] += signal.mention_count
        if signal.organization_id is not None:
            technology_orgs[(projected.technology_node_id, observed_date)].add(
                signal.organization_id
            )
        technology_sources[(projected.technology_node_id, observed_date)].add(
            signal.data_source_id
        )
        technology_nodes[projected.technology_node_id] = (projected, domain)
    return {
        "dates": dates,
        "domain_jobs": domain_jobs,
        "domain_mentions": domain_mentions,
        "domain_orgs": domain_orgs,
        "domain_sources": domain_sources,
        "technology_jobs": technology_jobs,
        "technology_mentions": technology_mentions,
        "technology_orgs": technology_orgs,
        "technology_sources": technology_sources,
        "technology_nodes": technology_nodes,
        "observed_dates": observed_dates,
    }


def _persist_daily_metrics(db: Session, context: ProjectionContext, aggregates: dict) -> int:
    """设计 §11.4：把按日触发指标落库（同一聚类运行幂等重建）。"""
    run_code = context.run.run_code
    db.execute(
        delete(TechnologyDailyTriggerMetric).where(
            TechnologyDailyTriggerMetric.clustering_run_code == run_code
        )
    )
    rows = 0
    domain_jobs = aggregates["domain_jobs"]
    for (domain, metric_date), job_ids in domain_jobs.items():
        db.add(
            TechnologyDailyTriggerMetric(
                metric_date=metric_date,
                technology_domain_code=domain,
                technology_node_id=DOMAIN_AGGREGATE_TECHNOLOGY_ID,
                trigger_document_count=len(job_ids),
                trigger_mention_count=aggregates["domain_mentions"][(domain, metric_date)],
                independent_org_count=len(aggregates["domain_orgs"][(domain, metric_date)]),
                independent_source_count=len(
                    aggregates["domain_sources"][(domain, metric_date)]
                ),
                clustering_run_code=run_code,
                calculation_version=DAILY_METRIC_CALCULATION_VERSION,
            )
        )
        rows += 1
    technology_jobs = aggregates["technology_jobs"]
    technology_nodes = aggregates["technology_nodes"]
    for (technology_id, metric_date), job_ids in technology_jobs.items():
        domain = technology_nodes[technology_id][1]
        db.add(
            TechnologyDailyTriggerMetric(
                metric_date=metric_date,
                technology_domain_code=domain,
                technology_node_id=technology_id,
                trigger_document_count=len(job_ids),
                trigger_mention_count=aggregates["technology_mentions"]
                [(technology_id, metric_date)],
                independent_org_count=len(
                    aggregates["technology_orgs"][(technology_id, metric_date)]
                ),
                independent_source_count=len(
                    aggregates["technology_sources"][(technology_id, metric_date)]
                ),
                clustering_run_code=run_code,
                calculation_version=DAILY_METRIC_CALCULATION_VERSION,
            )
        )
        rows += 1
    db.flush()
    return rows


def refresh_daily_trigger_metrics(db: Session, *, level_code: str = "L2", days: int = 45) -> int:
    """离线刷新按日触发指标（与热力图同一口径），返回落库行数。"""
    _validate_filters(None, level_code)
    if days != 45:
        raise GraphProjectionError("P0热力图固定使用45天窗口")
    context = _context(db)
    aggregates = _heatmap_aggregates(context, level_code=level_code, days=days)
    rows = _persist_daily_metrics(db, context, aggregates)
    db.commit()
    return rows


def _heat_cell(metric_date: date, job_ids: set[int], mention_count: int) -> dict:
    return {
        "metric_date": metric_date.isoformat(),
        "trigger_document_count": len(job_ids),
        "trigger_mention_count": mention_count,
    }


def _legend() -> list[dict]:
    return [
        {"domain_code": code, "domain_name": name, "color": color}
        for code, (name, color) in DOMAIN_LEDGER.items()
    ]


def _metadata(context: ProjectionContext) -> dict:
    return {
        "data_version": context.data_version,
        "projection_version": PROJECTION_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "target_date": context.run.target_date.isoformat(),
        "clustering_run_code": context.run.run_code,
        "evidence_policy": "accepted_technology_context_only",
    }


def _validate_filters(domain_code: str | None, level_code: str) -> None:
    if domain_code and domain_code not in DOMAIN_LEDGER:
        raise GraphProjectionError("技术域必须是T1至T7")
    if level_code not in {"L1", "L2", "L3"}:
        raise GraphProjectionError("P0图谱仅支持L1、L2或L3投影")


def _round(value: float, places: int) -> float:
    quantum = Decimal("1").scaleb(-places)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def _float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None
