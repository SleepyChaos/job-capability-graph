from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

BRIDGE_PATH = Path(__file__).resolve().parents[3] / "data" / "job_graph_bridge.json"


@lru_cache(maxsize=1)
def load_job_graph_bridge() -> dict[str, Any]:
    """Load the versioned, read-only bridge generated from the new job graph workbooks."""
    if not BRIDGE_PATH.exists():
        return {"schema_version": "job_graph_bridge_v1", "jobs": {}, "roles": {}}
    with BRIDGE_PATH.open(encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        return {"schema_version": "job_graph_bridge_v1", "jobs": {}, "roles": {}}
    return payload


def job_graph_association(
    *,
    source_job_id: str | None,
    job_code: str | None,
    job_title: str | None,
    company: str | None,
    required_capability_graph: dict,
) -> dict[str, Any]:
    """Join one matched JD to the new hierarchy, portrait and technology graph."""
    bridge = load_job_graph_bridge()
    job = (bridge.get("jobs") or {}).get(source_job_id or "")
    if not job:
        return {
            "status": "unlinked",
            "schema_version": bridge.get("schema_version", "job_graph_bridge_v1"),
            "source_job_id": source_job_id,
            "job_code": job_code,
            "job_title": job_title,
            "company": company,
            "standard_role": None,
            "hierarchy": None,
            "portrait": None,
            "technology_paths": [],
            "requirement_coverage": required_capability_graph,
            "message": "该岗位尚未在新版岗位图谱中找到 occ_id 对应关系。",
        }

    role = (bridge.get("roles") or {}).get(job.get("role_code"), {})
    hierarchy = {
        "direction": job.get("direction") or role.get("direction"),
        "category": job.get("category") or role.get("category"),
        "cluster_code": job.get("cluster_code") or role.get("cluster_code"),
        "cluster_name": job.get("cluster_name") or role.get("cluster_name"),
    }
    standard_role = {
        "role_code": job.get("role_code"),
        "name": job.get("role_name") or role.get("name"),
        "job_count": role.get("job_count", 0),
        "match_confidence": job.get("match_confidence"),
        "match_method": job.get("match_method"),
    }
    return {
        "status": "linked",
        "schema_version": bridge.get("schema_version", "job_graph_bridge_v1"),
        "source_job_id": source_job_id,
        "job_code": job_code,
        "job_title": job_title,
        "company": company,
        "standard_role": standard_role,
        "hierarchy": hierarchy,
        "portrait": role.get("portrait"),
        "technology_paths": job.get("technology_paths") or [],
        "requirement_coverage": required_capability_graph,
        "message": "已通过 occ_id 关联新版标准岗位、五维画像与技术分层。",
    }


@lru_cache(maxsize=1)
def job_graph_overview() -> dict[str, Any]:
    """Build compact, browser-friendly projections for the three new graph views."""
    bridge = load_job_graph_bridge()
    roles = bridge.get("roles") or {}
    jobs = bridge.get("jobs") or {}
    role_job_counts: dict[str, int] = {}
    technology_index: dict[str, dict[str, Any]] = {}
    company_index: dict[str, dict[str, Any]] = {}

    for job in jobs.values():
        role_code = job.get("role_code")
        if role_code:
            role_job_counts[role_code] = role_job_counts.get(role_code, 0) + 1
        company = job.get("company") or "企业信息未公开"
        company_item = company_index.setdefault(
            company,
            {"name": company, "job_count": 0, "role_codes": set()},
        )
        company_item["job_count"] += 1
        if role_code:
            company_item["role_codes"].add(role_code)

        seen_technology_codes = set()
        for technology in job.get("technology_paths") or []:
            path = technology.get("path") or []
            if not path:
                continue
            leaf = path[-1]
            technology_code = leaf.get("code")
            if not technology_code or technology_code in seen_technology_codes:
                continue
            seen_technology_codes.add(technology_code)
            item = technology_index.setdefault(
                technology_code,
                {
                    "code": technology_code,
                    "name": leaf.get("name") or technology_code,
                    "level": leaf.get("level"),
                    "path": path,
                    "job_count": 0,
                    "exact_evidence_count": 0,
                    "role_codes": set(),
                },
            )
            item["job_count"] += 1
            item["exact_evidence_count"] += int(bool(technology.get("evidence_grade")))
            if role_code:
                item["role_codes"].add(role_code)

    role_items = []
    hierarchy_sets: dict[str, dict[str, dict[str, set[str]]]] = {}
    for job in jobs.values():
        role_code = job.get("role_code")
        if not role_code:
            continue
        direction = job.get("direction") or "未分类方向"
        category = job.get("category") or "未分类类别"
        cluster_code = job.get("cluster_code") or "CL-NA"
        cluster_name = job.get("cluster_name") or "未分类岗位簇"
        cluster = f"{cluster_code}|{cluster_name}"
        hierarchy_sets.setdefault(direction, {}).setdefault(category, {}).setdefault(
            cluster, set()
        ).add(role_code)
    hierarchy = {
        direction: {
            category: {cluster: sorted(role_codes) for cluster, role_codes in clusters.items()}
            for category, clusters in categories.items()
        }
        for direction, categories in hierarchy_sets.items()
    }
    for role_code, role in roles.items():
        role_item = {
            "role_code": role_code,
            "name": role.get("name"),
            "direction": role.get("direction"),
            "category": role.get("category"),
            "cluster_code": role.get("cluster_code"),
            "cluster_name": role.get("cluster_name"),
            "job_count": role_job_counts.get(role_code, role.get("job_count", 0)),
        }
        role_items.append(role_item)

    technologies = []
    for item in technology_index.values():
        technologies.append(
            {
                **item,
                "role_codes": sorted(item["role_codes"]),
                "evidence_rate": round(item["exact_evidence_count"] / item["job_count"], 4),
            }
        )
    companies = [
        {**item, "role_codes": sorted(item["role_codes"])} for item in company_index.values()
    ]
    role_items.sort(key=lambda item: (-item["job_count"], item["name"] or ""))
    technologies.sort(key=lambda item: (-item["job_count"], item["code"]))
    companies.sort(key=lambda item: (-item["job_count"], item["name"]))
    return {
        "schema_version": bridge.get("schema_version", "job_graph_bridge_v1"),
        "source_version": bridge.get("source_version"),
        "metadata": {
            **(bridge.get("metadata") or {}),
            "direction_count": len(hierarchy),
            "category_count": len(
                {category for categories in hierarchy.values() for category in categories}
            ),
            "cluster_count": len(
                {
                    cluster
                    for categories in hierarchy.values()
                    for clusters in categories.values()
                    for cluster in clusters
                }
            ),
            "technology_count": len(technologies),
            "company_count": len(companies),
        },
        "hierarchy": hierarchy,
        "roles": role_items,
        "technologies": technologies,
        "companies": companies,
    }


def job_graph_role_detail(role_code: str) -> dict[str, Any] | None:
    bridge = load_job_graph_bridge()
    role = (bridge.get("roles") or {}).get(role_code)
    if not role:
        return None
    jobs = [
        {"occ_id": occ_id, **job}
        for occ_id, job in (bridge.get("jobs") or {}).items()
        if job.get("role_code") == role_code
    ]
    technology_index: dict[str, dict[str, Any]] = {}
    company_counts: dict[str, int] = {}
    for job in jobs:
        company = job.get("company") or "企业信息未公开"
        company_counts[company] = company_counts.get(company, 0) + 1
        for technology in job.get("technology_paths") or []:
            path = technology.get("path") or []
            if not path:
                continue
            leaf = path[-1]
            code = leaf.get("code")
            if not code:
                continue
            item = technology_index.setdefault(
                code,
                {
                    "code": code,
                    "name": leaf.get("name") or code,
                    "path": path,
                    "job_count": 0,
                    "exact_evidence_count": 0,
                    "hit_terms": [],
                },
            )
            item["job_count"] += 1
            item["exact_evidence_count"] += int(bool(technology.get("evidence_grade")))
            item["hit_terms"] = list(
                dict.fromkeys([*item["hit_terms"], *(technology.get("hit_terms") or [])])
            )[:12]
    technologies = sorted(
        technology_index.values(), key=lambda item: (-item["job_count"], item["code"])
    )
    companies = sorted(
        ({"name": name, "job_count": count} for name, count in company_counts.items()),
        key=lambda item: (-item["job_count"], item["name"]),
    )
    jobs.sort(key=lambda item: (item.get("company") or "", item.get("title") or ""))
    return {
        "role": {"role_code": role_code, **role},
        "technologies": technologies,
        "companies": companies,
        "jobs": jobs,
    }
