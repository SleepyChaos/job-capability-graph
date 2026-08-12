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

PROJECTION_VERSION = "graph_projection_p0_v1"
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


def relation_graph(
    db: Session,
    *,
    cluster_domain_code: str | None = None,
    capability_domain_code: str | None = None,
    capability_level_code: str = "L2",
    cluster_limit: int = 12,
    capabilities_per_cluster: int = 8,
    # Compatibility aliases for scripts and callers written before the
    # relation graph gained independent role/capability filters.
    domain_code: str | None = None,
    level_code: str | None = None,
) -> dict:
    if capability_domain_code is None:
        capability_domain_code = domain_code
    if level_code is not None and capability_level_code == "L2":
        capability_level_code = level_code
    context = _context(db)
    _validate_filters(cluster_domain_code, capability_level_code)
    _validate_filters(capability_domain_code, capability_level_code)
    clusters = _active_clusters(db, context.run.clustering_run_id)
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

        capability_metrics = _cluster_capability_metrics(
            context,
            cluster,
            memberships.get(cluster.job_cluster_version_id, set()),
            signal_by_job,
            level_code=capability_level_code,
            recent_job_count=10,
        )
        if capability_domain_code:
            capability_metrics = [
                item
                for item in capability_metrics
                if item["domain_code"] == capability_domain_code
            ]
        projected.append((cluster, role_domain, capability_metrics[:capabilities_per_cluster]))
        if len(projected) >= cluster_limit:
            break

    capability_nodes = {}
    role_nodes = []
    edges = []
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
    return {
        **_metadata(context),
        "filters": {
            "cluster_domain_code": cluster_domain_code,
            "capability_domain_code": capability_domain_code,
            "capability_level_code": capability_level_code,
            "cluster_limit": cluster_limit,
            "capabilities_per_cluster": capabilities_per_cluster,
        },
        "legend": _legend(),
        "role_nodes": role_nodes,
        "capability_nodes": list(capability_nodes.values()),
        "edges": edges,
        "rendering": {
            "artifact_family": "node_link",
            "primary_route": "g6_force",
            "fallback": "edge_table",
            "layout_owner": "frontend_g6_force",
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
