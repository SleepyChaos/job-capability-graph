import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel
from sqlalchemy import delete, distinct, func, select
from sqlalchemy.orm import Session

from app.modules.clustering.models import (
    JobClusteringRun,
    JobClusterMember,
    JobClusterVersion,
)
from app.modules.graph.models import (
    DOMAIN_AGGREGATE_TECHNOLOGY_ID,
    TechnologyDailyTriggerMetric,
)
from app.modules.job.models import (
    JobParseRun,
    JobPosting,
    JobRequirement,
    Organization,
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

INDUSTRY_STAGE_LEDGER = {
    "upstream": ("上游", "#4f7cff"),
    "midstream": ("中游", "#12a594"),
    "downstream": ("下游", "#f59e42"),
    "support": ("横向支撑", "#8b72d8"),
    "unclassified": ("待归类", "#94a3b8"),
}


def _industry_stage(value: object) -> str:
    text = str(value or "").strip()
    if text.startswith("上游"):
        return "upstream"
    if text.startswith("中游"):
        return "midstream"
    if text.startswith("下游"):
        return "downstream"
    if "横向" in text or any(word in text for word in ("政策", "生态", "标准", "检测")):
        return "support"
    return "unclassified"


def _industry_category(value: object) -> str:
    text = str(value or "").strip()
    for separator in ("-", "—", "－", ":", "："):
        if separator in text:
            suffix = text.split(separator, 1)[1].strip()
            if suffix:
                return suffix
    return text if text and text not in {"上游", "中游", "下游", "横向支撑"} else "其他"


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


def industry_chain_summary(db: Session) -> dict:
    """Build one governed navigation index for every graph projection."""
    jobs = list(db.scalars(select(JobPosting).order_by(JobPosting.job_posting_id)))
    organizations = {
        organization.organization_id: organization
        for organization in db.scalars(select(Organization))
    }
    try:
        context = _context(db)
        clusters = _active_clusters(db, context.run.clustering_run_id)
        memberships = _cluster_memberships(
            db, [cluster.job_cluster_version_id for cluster in clusters]
        )
        data_version = context.data_version
        target_date = context.run.target_date.isoformat()
    except GraphProjectionError:
        clusters = []
        memberships = {}
        data_version = "uninitialized"
        target_date = ""

    job_stage: dict[int, str] = {}
    job_category: dict[int, str] = {}
    stage_jobs: dict[str, set[int]] = defaultdict(set)
    stage_orgs: dict[str, set[int]] = defaultdict(set)
    category_jobs: dict[tuple[str, str], set[int]] = defaultdict(set)
    category_orgs: dict[tuple[str, str], set[int]] = defaultdict(set)
    org_job_counts: Counter[tuple[str, int]] = Counter()
    for job in jobs:
        metadata = job.source_metadata_json or {}
        raw_level = metadata.get("industry_chain_level")
        stage = _industry_stage(raw_level)
        category = _industry_category(raw_level)
        job_stage[job.job_posting_id] = stage
        job_category[job.job_posting_id] = category
        stage_jobs[stage].add(job.job_posting_id)
        category_jobs[(stage, category)].add(job.job_posting_id)
        if job.organization_id is not None:
            stage_orgs[stage].add(job.organization_id)
            category_orgs[(stage, category)].add(job.organization_id)
            org_job_counts[(stage, job.organization_id)] += 1

    cluster_stage: dict[int, str] = {}
    cluster_category: dict[int, str] = {}
    stage_clusters: dict[str, list[JobClusterVersion]] = defaultdict(list)
    category_clusters: dict[tuple[str, str], list[JobClusterVersion]] = defaultdict(list)
    for cluster in clusters:
        member_ids = memberships.get(cluster.job_cluster_version_id, set())
        stage = Counter(job_stage.get(job_id, "unclassified") for job_id in member_ids).most_common(1)
        stage_code = stage[0][0] if stage else "unclassified"
        category = Counter(job_category.get(job_id, "其他") for job_id in member_ids).most_common(1)
        category_name = category[0][0] if category else "其他"
        cluster_stage[cluster.job_cluster_version_id] = stage_code
        cluster_category[cluster.job_cluster_version_id] = category_name
        stage_clusters[stage_code].append(cluster)
        category_clusters[(stage_code, category_name)].append(cluster)

    technology_rows = db.execute(
        select(JobRequirement.job_posting_id, JobRequirement.technology_node_id).distinct()
    ).all()
    stage_technologies: dict[str, set[int]] = defaultdict(set)
    category_technologies: dict[tuple[str, str], set[int]] = defaultdict(set)
    for job_id, technology_id in technology_rows:
        stage = job_stage.get(job_id, "unclassified")
        category = job_category.get(job_id, "其他")
        if technology_id is not None:
            stage_technologies[stage].add(technology_id)
            category_technologies[(stage, category)].add(technology_id)

    stages = []
    for stage_code in INDUSTRY_STAGE_LEDGER:
        name, color = INDUSTRY_STAGE_LEDGER[stage_code]
        category_names = sorted(
            {category for stage, category in category_jobs if stage == stage_code},
            key=lambda category: (-len(category_jobs[(stage_code, category)]), category),
        )
        top_org_ids = sorted(
            stage_orgs[stage_code],
            key=lambda org_id: (-org_job_counts[(stage_code, org_id)], org_id),
        )[:5]
        top_clusters = sorted(
            stage_clusters[stage_code], key=lambda cluster: (-cluster.member_count, cluster.cluster_label)
        )[:5]
        stages.append({
            "code": stage_code,
            "name": name,
            "color": color,
            "job_count": len(stage_jobs[stage_code]),
            "organization_count": len(stage_orgs[stage_code]),
            "cluster_count": len(stage_clusters[stage_code]),
            "technology_count": len(stage_technologies[stage_code]),
            "top_organizations": [
                {
                    "code": organizations[org_id].organization_code,
                    "name": organizations[org_id].canonical_name,
                    "job_count": org_job_counts[(stage_code, org_id)],
                }
                for org_id in top_org_ids if org_id in organizations
            ],
            "top_clusters": [
                {"code": cluster.stable_cluster_code, "label": cluster.cluster_label, "job_count": cluster.member_count}
                for cluster in top_clusters
            ],
            "categories": [
                {
                    "name": category,
                    "job_count": len(category_jobs[(stage_code, category)]),
                    "organization_count": len(category_orgs[(stage_code, category)]),
                    "cluster_count": len(category_clusters[(stage_code, category)]),
                    "technology_count": len(category_technologies[(stage_code, category)]),
                }
                for category in category_names
            ],
        })
    return {"data_version": data_version, "target_date": target_date, "stages": stages}


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
    industry_stage: str | None = None,
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
    # A relation graph without capability nodes has no useful relationships.
    # Reserve half of the budget for de-duplicated capabilities instead of
    # allowing role clusters to consume the entire canvas.
    role_budget = 1 if mode == "focus" else max(1, node_budget // 2)
    effective_cluster_limit = min(cluster_limit, role_budget)
    memberships = _cluster_memberships(db, [item.job_cluster_version_id for item in clusters])
    if industry_stage:
        if industry_stage not in INDUSTRY_STAGE_LEDGER:
            raise GraphProjectionError("产业链层级编码无效")
        stage_by_job = {
            job_id: _industry_stage(metadata.get("industry_chain_level"))
            for job_id, metadata in db.execute(
                select(JobPosting.job_posting_id, JobPosting.source_metadata_json)
            ).all()
            for metadata in [metadata or {}]
        }
        clusters = [
            cluster for cluster in clusters
            if Counter(
                stage_by_job.get(job_id, "unclassified")
                for job_id in memberships.get(cluster.job_cluster_version_id, set())
            ).most_common(1)
            and Counter(
                stage_by_job.get(job_id, "unclassified")
                for job_id in memberships.get(cluster.job_cluster_version_id, set())
            ).most_common(1)[0][0] == industry_stage
        ]
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

    capability_nodes: dict[int, dict] = {}
    role_nodes: list[dict] = []
    edges: list[dict] = []
    capability_budget = max(0, node_budget - len(projected))
    cluster_top_l2: list[tuple[str, int | None]] = []
    for cluster, primary_domain, metrics in projected:
        cluster_id = f"cluster:{cluster.stable_cluster_code}"
        role_nodes.append(
            {
                "id": cluster_id,
                "type": "job_cluster",
                "label": cluster.cluster_label,
                "domain_code": primary_domain,
                "metrics": {
                    "member_count": cluster.member_count,
                    "organization_count": cluster.independent_organization_count,
                    "coherence_score": _float(cluster.coherence_score),
                },
                "evidence_count": cluster.member_count,
                "layer": 0,
                "parent_ids": [],
            }
        )
        top_l2_id: int | None = None
        l2_metrics = [m for m in metrics if m["level_code"] == "L2"]
        if l2_metrics:
            top_l2_id = l2_metrics[0]["technology_node_id"]
        cluster_top_l2.append((cluster_id, top_l2_id))
        for metric in metrics:
            technology_id = metric["technology_node_id"]
            if technology_id not in capability_nodes and len(capability_nodes) >= capability_budget:
                continue
            capability_node = capability_nodes.get(technology_id)
            if capability_node is None:
                domain_code = metric["domain_code"]
                level_code = metric["level_code"]
                layer = _capability_layer(level_code)
                parent_ids = _capability_parent_ids(
                    context, technology_id, level_code, domain_code
                )
                capability_node = {
                    "id": f"technology:{technology_id}",
                    "type": "technology",
                    "label": metric["technology_name"],
                    "domain_code": domain_code,
                    "level_code": level_code,
                    "metrics": {
                        "supporting_job_count": 0,
                        "recent_activity": 0,
                    },
                    "evidence_count": 0,
                    "layer": layer,
                    "parent_ids": parent_ids,
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
                    "source": cluster_id,
                    "target": f"technology:{technology_id}",
                    "relation_type": "important_technology",
                    "importance": metric["importance"],
                    "recent_activity": metric["recent_activity"],
                    "supporting_job_count": metric["supporting_job_count"],
                    "coverage_rate": metric["coverage_rate"],
                    "evidence_job_codes": metric["evidence_job_codes"],
                }
            )
    for cluster_id, top_l2_id in cluster_top_l2:
        if top_l2_id is not None and top_l2_id in capability_nodes:
            edges.append(
                {
                    "id": f"edge:major:{cluster_id.removeprefix('cluster:')}:{top_l2_id}",
                    "source": cluster_id,
                    "target": f"technology:{top_l2_id}",
                    "relation_type": "major_cluster_capability",
                    "importance": 100.0,
                    "recent_activity": 100.0,
                    "supporting_job_count": 0,
                    "coverage_rate": 1.0,
                    "evidence_job_codes": [],
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
        layer = _capability_layer(technology.level_code)
        parent_ids = _capability_parent_ids(
            context, technology_id, technology.level_code, domain_code
        )
        capability_nodes[technology_id] = {
            "id": f"technology:{technology_id}",
            "type": "technology",
            "label": technology.technology_name,
            "domain_code": domain_code,
            "level_code": technology.level_code,
            "metrics": {"supporting_job_count": 0, "recent_activity": 0},
            "evidence_count": 0,
            "layer": layer,
            "parent_ids": parent_ids,
        }
    for cap_node in capability_nodes.values():
        level_code = cap_node.get("level_code")
        if level_code == "L2":
            parent_ids = cap_node.get("parent_ids", [])
            for pid in parent_ids:
                edges.append(
                    {
                        "id": f"edge:dg:{pid}:{cap_node['id']}",
                        "source": pid,
                        "target": cap_node["id"],
                        "relation_type": "dg_membership",
                        "style": "dashed",
                        "importance": 50.0,
                        "recent_activity": 0,
                        "supporting_job_count": 0,
                        "coverage_rate": 0,
                        "evidence_job_codes": [],
                    }
                )
        elif level_code in {"L3", "L4"}:
            parent_ids = cap_node.get("parent_ids", [])
            for pid in parent_ids:
                if pid.startswith("technology:"):
                    edges.append(
                        {
                            "id": f"edge:hierarchy:{pid}:{cap_node['id']}",
                            "source": pid,
                            "target": cap_node["id"],
                            "relation_type": "hierarchy",
                            "importance": 80.0,
                            "recent_activity": 0,
                            "supporting_job_count": 0,
                            "coverage_rate": 0,
                            "evidence_job_codes": [],
                        }
                    )
    domain_group_nodes: list[dict] = []
    used_domains: set[str] = set()
    for cap_node in capability_nodes.values():
        domain_code = cap_node.get("domain_code")
        if domain_code and domain_code in DOMAIN_LEDGER:
            used_domains.add(domain_code)
    for cluster in role_nodes:
        domain_code = cluster.get("domain_code")
        if domain_code and domain_code in DOMAIN_LEDGER:
            used_domains.add(domain_code)
    for domain_code in sorted(used_domains):
        name, color = DOMAIN_LEDGER[domain_code]
        domain_group_nodes.append(
            {
                "id": f"dg-{domain_code}",
                "name": name,
                "code": domain_code,
                "color": color,
                "layer": 1,
                "parent_ids": [],
            }
        )
    # Layer numbering for dagre LR: 岗位簇(left, 0) → T1 领域分组(1) → L2(2) → L3(3)。
    for cluster in role_nodes:
        cluster["layer"] = 0
    for dg in domain_group_nodes:
        dg["layer"] = 1
    for cap in capability_nodes.values():
        level_code = cap.get("level_code")
        if level_code == "L2":
            cap["layer"] = 2
        elif level_code in {"L3", "L4"}:
            cap["layer"] = 3
    return {
        **_metadata(context),
        "filters": {
            "cluster_domain_code": cluster_domain_code,
            "capability_domain_code": capability_domain_code,
            "capability_level_code": capability_level_code,
            "cluster_limit": effective_cluster_limit,
            "capabilities_per_cluster": capabilities_per_cluster,
            "node_budget": node_budget,
            "role_budget": effective_cluster_limit,
            "capability_budget": capability_budget,
            "min_supporting_job_count": min_supporting_job_count,
            "mode": mode,
            "focus_node_id": focus_node_id,
            "industry_stage": industry_stage,
        },
        "legend": _legend(),
        "role_nodes": role_nodes,
        "capability_nodes": list(capability_nodes.values()),
        "domain_group_nodes": domain_group_nodes,
        "edges": edges,
        "layout": {
            "mode": "layered_dagre",
            "rankdir": "LR",
        },
        "layout_mode": "layered_dagre",
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


def _capability_layer(level_code: str) -> int:
    if level_code == "L2":
        return 2
    if level_code in {"L3", "L4"}:
        return 3
    return 2


def _capability_parent_ids(
    context: ProjectionContext, technology_id: int, level_code: str, domain_code: str
) -> list[str]:
    if level_code == "L2":
        return [f"dg-{domain_code}"]
    if level_code in {"L3", "L4"}:
        node = context.nodes.get(technology_id)
        if node and node.parent_technology_node_id and node.parent_technology_node_id in context.nodes:
            parent = context.nodes[node.parent_technology_node_id]
            if level_code == "L4" and parent.level_code == "L3" and parent.parent_technology_node_id:
                grandparent = context.nodes.get(parent.parent_technology_node_id)
                if grandparent and grandparent.level_code == "L2":
                    return [f"technology:{parent.parent_technology_node_id}"]
            return [f"technology:{node.parent_technology_node_id}"]
        return [f"dg-{domain_code}"]
    return [f"dg-{domain_code}"]


# ------------------------- 企业 ↔ 技术 图谱 -------------------------

def org_tech_graph(
    db: Session,
    *,
    capability_domain_code: str | None = None,
    capability_level_code: str = "L2",
    org_limit: int = 40,
    capabilities_per_org: int = 20,
    min_supporting_job_count: int = 1,
    industry_stage: str | None = None,
) -> dict:
    """方案 B 分层企业-技术图：机构(layer 0) → T1 领域分组(layer 1) → L2(layer 2) → L3(layer 3)。"""
    if min_supporting_job_count < 1:
        raise GraphProjectionError("最小支持岗位数至少为 1")
    context = _context(db)
    _validate_filters(capability_domain_code, capability_level_code)

    # Aggregate org_id -> {technology_id -> job_count}
    rows = db.execute(
        select(
            JobPosting.organization_id,
            JobRequirement.technology_node_id,
            JobRequirement.job_posting_id,
            JobPosting.source_metadata_json,
        )
        .join(JobPosting, JobPosting.job_posting_id == JobRequirement.job_posting_id)
        .where(
            JobPosting.organization_id.is_not(None),
            JobRequirement.technology_node_id.is_not(None),
        )
        .distinct()
    ).all()
    org_tech_counts: Counter[tuple[int, int]] = Counter()
    for oid, tid, _job_id, metadata in rows:
        if industry_stage and _industry_stage((metadata or {}).get("industry_chain_level")) != industry_stage:
            continue
        org_tech_counts[(int(oid), int(tid))] += 1
    org_tech: dict[int, dict[int, int]] = {}
    techs_found: set[int] = set()
    for (oid, tid), cnt in org_tech_counts.items():
        if cnt < min_supporting_job_count:
            continue
        org_tech.setdefault(int(oid), {})[int(tid)] = int(cnt)
        techs_found.add(int(tid))

    org_ids_sorted = sorted(org_tech.keys(), key=lambda oid: (-len(org_tech[oid]), oid))[:org_limit]
    org_ids = set(org_ids_sorted)

    org_rows = db.execute(
        select(Organization.organization_id, Organization.organization_code, Organization.canonical_name, Organization.organization_type_code, Organization.province_name, Organization.city_name, Organization.organization_status_code)
        .where(Organization.organization_id.in_(list(org_ids)))
    ).all()
    org_info: dict[int, dict] = {
        oid: {"code": code, "name": name, "type": type_code, "province": prov, "city": city, "status": status}
        for oid, code, name, type_code, prov, city, status in org_rows
    }

    # Level filter
    tech_nodes_view: dict[int, TechnologyNode] = {
        tid: t for tid, t in context.nodes.items() if tid in techs_found
    }
    # For L3/L4, traverse ancestors to include L2
    expanded_techs: set[int] = set()
    for tid in techs_found:
        node = tech_nodes_view.get(tid)
        if not node:
            continue
        if node.level_code == capability_level_code:
            expanded_techs.add(tid)
            if capability_level_code in {"L3", "L4"} and node.parent_technology_node_id:
                parent = context.nodes.get(node.parent_technology_node_id)
                if parent and parent.level_code == "L2":
                    expanded_techs.add(parent.technology_node_id)
        elif capability_level_code == "L2" and node.level_code in {"L3", "L4"}:
            # When viewing L2, roll L3/L4 up to L2 parent
            if node.parent_technology_node_id:
                parent = context.nodes.get(node.parent_technology_node_id)
                if parent and parent.level_code == "L2":
                    expanded_techs.add(parent.technology_node_id)
                    orig_cnt = org_tech
                    # Accumulate roll-up counts
                    for oid in list(org_tech.keys()):
                        if tid in org_tech.get(oid, {}):
                            org_tech[oid][parent.technology_node_id] = org_tech[oid].get(parent.technology_node_id, 0) + org_tech[oid][tid]
        if capability_level_code == "L2" and node.level_code == "L2":
            expanded_techs.add(tid)

    if capability_domain_code:
        expanded_techs = {tid for tid in expanded_techs if context.primary_domains.get(tid) == capability_domain_code}

    org_nodes: list[dict] = []
    tech_nodes: dict[int, dict] = {}
    edges: list[dict] = []
    used_domains: set[str] = set()

    for oid in org_ids_sorted:
        info = org_info.get(oid, {"code": f"ORG{oid}", "name": f"机构{oid}", "type": "unknown", "province": None, "city": None, "status": "active"})
        org_id = f"org:{info['code']}"
        org_nodes.append(
            {
                "id": org_id,
                "type": "organization",
                "label": info["name"],
                "code": info["code"],
                "province": info["province"],
                "city": info["city"],
                "org_type": info["type"],
                "status": info["status"],
                "layer": 0,
                "parent_ids": [],
                "metrics": {"technology_count": 0, "job_count": 0, "domain_count": 0},
            }
        )
        org_metrics = org_nodes[-1]["metrics"]
        tc_list = sorted((org_tech.get(oid, {}).items()), key=lambda kv: kv[1], reverse=True)
        org_techs: list[int] = []
        org_domains: set[str] = set()
        total_jobs = 0
        for tid, cnt in tc_list:
            if tid not in expanded_techs:
                continue
            if len(org_techs) >= capabilities_per_org:
                break
            node = context.nodes.get(tid)
            if not node:
                continue
            domain_code = context.primary_domains.get(tid, "T7")
            if capability_domain_code and domain_code != capability_domain_code:
                continue
            org_techs.append(tid)
            org_domains.add(domain_code)
            used_domains.add(domain_code)
            total_jobs += cnt
            if tid not in tech_nodes:
                layer = 2 if node.level_code == "L2" else (3 if node.level_code in {"L3", "L4"} else 2)
                tech_nodes[tid] = {
                    "id": f"technology:{tid}",
                    "type": "technology",
                    "label": node.technology_name,
                    "code": node.technology_code,
                    "level_code": node.level_code,
                    "domain_code": domain_code,
                    "layer": layer,
                    "parent_ids": [f"dg-{domain_code}"] if node.level_code == "L2" else (
                        [f"technology:{node.parent_technology_node_id}"] if node.parent_technology_node_id and node.parent_technology_node_id in context.nodes else [f"dg-{domain_code}"]
                    ),
                    "metrics": {"supporting_org_count": 0, "job_count": 0},
                }
            tech_nodes[tid]["metrics"]["supporting_org_count"] += 1
            tech_nodes[tid]["metrics"]["job_count"] += cnt
            edges.append(
                {
                    "id": f"edge-org-tech:{info['code']}:{tid}",
                    "source": org_id,
                    "target": f"technology:{tid}",
                    "relation_type": "org_adopts_tech",
                    "job_count": cnt,
                }
            )
        org_metrics["technology_count"] = len(org_techs)
        org_metrics["job_count"] = total_jobs
        org_metrics["domain_count"] = len(org_domains)

    # Add L2 ancestor edges for L3 nodes, and domain grouping edges
    domain_group_nodes: list[dict] = []
    for tid, tnode in list(tech_nodes.items()):
        if tnode["level_code"] in {"L3", "L4"}:
            for pid in tnode["parent_ids"]:
                if pid.startswith("technology:"):
                    parent_tid = int(pid.removeprefix("technology:"))
                    if parent_tid not in tech_nodes and parent_tid in context.nodes:
                        pnode_db = context.nodes[parent_tid]
                        domain_code = context.primary_domains.get(parent_tid, "T7")
                        used_domains.add(domain_code)
                        tech_nodes[parent_tid] = {
                            "id": f"technology:{parent_tid}",
                            "type": "technology",
                            "label": pnode_db.technology_name,
                            "code": pnode_db.technology_code,
                            "level_code": pnode_db.level_code,
                            "domain_code": domain_code,
                            "layer": 2,
                            "parent_ids": [f"dg-{domain_code}"],
                            "metrics": {"supporting_org_count": 0, "job_count": 0},
                        }
                    edges.append(
                        {
                            "id": f"edge-hierarchy:{pid}:{tnode['id']}",
                            "source": pid,
                            "target": tnode["id"],
                            "relation_type": "hierarchy",
                        }
                    )
    for tnode in tech_nodes.values():
        if tnode["level_code"] == "L2":
            for pid in tnode["parent_ids"]:
                if pid.startswith("dg-"):
                    used_domains.add(pid.removeprefix("dg-"))
    for domain_code in sorted(used_domains):
        if domain_code not in DOMAIN_LEDGER:
            continue
        name, color = DOMAIN_LEDGER[domain_code]
        domain_group_nodes.append(
            {
                "id": f"dg-{domain_code}",
                "name": name,
                "code": domain_code,
                "color": color,
                "layer": 1,
                "parent_ids": [],
            }
        )
    # dg → L2 edges
    for tnode in tech_nodes.values():
        if tnode["level_code"] == "L2":
            for pid in tnode["parent_ids"]:
                if pid.startswith("dg-"):
                    edges.append(
                        {
                            "id": f"edge-dg-membership:{pid}:{tnode['id']}",
                            "source": pid,
                            "target": tnode["id"],
                            "relation_type": "dg_membership",
                            "style": "dashed",
                        }
                    )

    return {
        "filters": {
            "industry_stage": industry_stage,
            "capability_domain_code": capability_domain_code,
            "capability_level_code": capability_level_code,
            "org_limit": org_limit,
            "capabilities_per_org": capabilities_per_org,
            "min_supporting_job_count": min_supporting_job_count,
        },
        "org_nodes": org_nodes,
        "domain_group_nodes": domain_group_nodes,
        "capability_nodes": list(tech_nodes.values()),
        "edges": edges,
        "layout": {"mode": "layered_dagre", "rankdir": "LR"},
        "layout_mode": "layered_dagre",
    }


# ------------------------- 能力 → 岗位簇 排序（GraphRelationsPage Tab 2） -------------------------

class CapabilityToClusterRow(BaseModel):
    """一行：某个 L2/L3 技术词 → 需要它的岗位簇排序"""
    technology_node_id: int
    technology_code: str
    technology_name: str
    level_code: str
    domain_code: str
    domain_name: str | None
    supporting_job_count: int
    ranked_clusters: list[dict]  # [{code,label,importance,coverage_rate,supporting_job_count}]


def capability_to_cluster_ranking(
    db: Session,
    *,
    capability_domain_code: str | None = None,
    capability_level_code: str = "L2",
    min_supporting_job_count: int = 1,
    limit: int = 300,
) -> dict:
    context = _context(db)
    _validate_filters(capability_domain_code, capability_level_code)
    clusters = _active_clusters(db, context.run.clustering_run_id)
    memberships = _cluster_memberships(db, [item.job_cluster_version_id for item in clusters])
    signal_by_job = _signals_by_job(context.signals)

    # tech_id -> sorted list of (cluster, metric_dict)
    tech_to_cluster: dict[int, list[tuple[JobClusterVersion, dict]]] = {}
    for cluster in clusters:
        metrics = _cluster_capability_metrics(
            context,
            cluster,
            memberships.get(cluster.job_cluster_version_id, set()),
            signal_by_job,
            level_code=capability_level_code,
            recent_job_count=10,
        )
        if capability_domain_code:
            metrics = [m for m in metrics if m["domain_code"] == capability_domain_code]
        metrics = [m for m in metrics if m["supporting_job_count"] >= min_supporting_job_count]
        for m in metrics:
            tech_to_cluster.setdefault(m["technology_node_id"], []).append((cluster, m))

    rows: list[CapabilityToClusterRow] = []
    for tid, pairs in tech_to_cluster.items():
        node = context.nodes.get(tid)
        if not node:
            continue
        domain_code = context.primary_domains.get(tid, "T7")
        if capability_domain_code and domain_code != capability_domain_code:
            continue
        total_jobs = sum(int(p[1]["supporting_job_count"]) for p in pairs)
        ranked = sorted(pairs, key=lambda pp: (-pp[1]["importance"], -pp[1]["supporting_job_count"]))
        rows.append(
            CapabilityToClusterRow(
                technology_node_id=tid,
                technology_code=node.technology_code,
                technology_name=node.technology_name,
                level_code=node.level_code,
                domain_code=domain_code,
                domain_name=DOMAIN_LEDGER.get(domain_code, (None, None))[0],
                supporting_job_count=total_jobs,
                ranked_clusters=[
                    {
                        "code": c.stable_cluster_code,
                        "label": c.cluster_label,
                        "importance": m["importance"],
                        "coverage_rate": m["coverage_rate"],
                        "supporting_job_count": m["supporting_job_count"],
                    }
                    for c, m in ranked
                ],
            )
        )
    rows.sort(key=lambda r: (-r.supporting_job_count, r.technology_code))
    return {
        "filters": {
            "capability_domain_code": capability_domain_code,
            "capability_level_code": capability_level_code,
            "min_supporting_job_count": min_supporting_job_count,
            "limit": limit,
        },
        "total": len(rows),
        "rows": [r.model_dump() for r in rows[:limit]],
    }
