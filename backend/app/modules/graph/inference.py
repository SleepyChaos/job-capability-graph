"""Lightweight, evidence-preserving inference for the static job knowledge graph.

The graph builder already publishes governed fact relations:

* job -> L4 technology terms
* job -> standard role
* L4 -> L3 -> L2 -> L1 technology hierarchy

This module keeps those facts unchanged and derives two separate relation sets:

* R1: a job that directly matches an L4 term also relates to its L3/L2/L1 ancestors;
* R2: standard-role/technology associations aggregated through supporting jobs.

The functions are deliberately independent of a graph database so the current JSON
build and frontend can remain unchanged.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import hashlib
from typing import Any


RULE_TECH_HIERARCHY = "R1_TECH_HIERARCHY_INHERITANCE"
RULE_ROLE_TECH = "R2_ROLE_TECH_BY_JD"
LEVEL_ORDER = {"L1": 1, "L2": 2, "L3": 3, "L4": 4}


class GraphInferenceError(ValueError):
    """Raised when the source graph cannot support safe inference."""


def _relation_id(rule_id: str, source_id: str, target_id: str) -> str:
    raw = f"{rule_id}|{source_id}|{target_id}".encode("utf-8")
    return f"inference-{hashlib.sha1(raw).hexdigest()[:18]}"


def _as_id_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return sorted({str(item).strip() for item in value if str(item).strip()})


def _technology_path(
    start_id: str,
    technology_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[list[str], str | None]:
    """Return start-to-root node IDs and an optional missing-parent warning.

    A cycle is treated as a hard error. Continuing through a cyclic taxonomy would
    make every downstream relation unreliable.
    """

    path: list[str] = []
    visited: set[str] = set()
    current_id = start_id
    missing_parent: str | None = None

    while current_id:
        if current_id in visited:
            cycle = " -> ".join([*path, current_id])
            raise GraphInferenceError(f"technology hierarchy cycle detected: {cycle}")
        visited.add(current_id)

        node = technology_by_id.get(current_id)
        if node is None:
            missing_parent = current_id
            break
        path.append(current_id)
        current_id = str(node.get("parentId") or "").strip()

    return path, missing_parent


def infer_graph_relations(
    graph: Mapping[str, Any],
    *,
    generated_at: str | None = None,
    source_sha256: str | None = None,
) -> dict[str, Any]:
    """Derive R1 and R2 relations without mutating ``graph``.

    ``coverage`` uses every JD assigned to the standard role as the denominator,
    including JDs without a technology match. This makes it a sample coverage
    measure rather than an accuracy score.
    """

    raw_technologies = graph.get("technologyNodes")
    raw_jobs = graph.get("jobs")
    raw_roles = graph.get("standardRoles")
    if not isinstance(raw_technologies, list) or not isinstance(raw_jobs, list):
        raise GraphInferenceError("source graph must contain technologyNodes and jobs lists")
    if not isinstance(raw_roles, list):
        raw_roles = []

    warnings: set[str] = set()
    technology_by_id: dict[str, Mapping[str, Any]] = {}
    for node in raw_technologies:
        if not isinstance(node, Mapping):
            continue
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            continue
        if node_id in technology_by_id:
            existing = technology_by_id[node_id]
            existing_structure = (
                str(existing.get("level") or ""),
                str(existing.get("parentId") or ""),
            )
            incoming_structure = (
                str(node.get("level") or ""),
                str(node.get("parentId") or ""),
            )
            if existing_structure != incoming_structure:
                raise GraphInferenceError(
                    f"duplicate technology node {node_id} has conflicting hierarchy"
                )
            warnings.add(
                f"duplicate technology node {node_id} has the same hierarchy; first row kept"
            )
            continue
        technology_by_id[node_id] = node

    role_by_id = {
        str(role.get("id")): role
        for role in raw_roles
        if isinstance(role, Mapping) and role.get("id")
    }

    jobs: list[Mapping[str, Any]] = []
    seen_job_ids: set[str] = set()
    for job in raw_jobs:
        if not isinstance(job, Mapping):
            continue
        job_id = str(job.get("id") or "").strip()
        if not job_id:
            continue
        if job_id in seen_job_ids:
            raise GraphInferenceError(f"duplicate job id: {job_id}")
        seen_job_ids.add(job_id)
        jobs.append(job)
    job_by_id = {str(job["id"]): job for job in jobs}

    role_job_ids: dict[str, set[str]] = defaultdict(set)
    for job in jobs:
        role_id = str(job.get("standardRoleId") or "").strip()
        if role_id:
            role_job_ids[role_id].add(str(job["id"]))

    direct_technology_job_ids: set[str] = set()

    # (job, ancestor) -> supporting L4 terms and one deterministic path.
    r1_support_terms: dict[tuple[str, str], set[str]] = defaultdict(set)
    r1_paths: dict[tuple[str, str], list[str]] = {}

    # (role, technology) -> jobs and direct L4 terms supporting the derived relation.
    r2_job_ids: dict[tuple[str, str], set[str]] = defaultdict(set)
    r2_occ_ids: dict[tuple[str, str], set[str]] = defaultdict(set)
    r2_term_ids: dict[tuple[str, str], set[str]] = defaultdict(set)

    for job in jobs:
        job_id = str(job["id"])
        occ_id = str(job.get("occId") or "").strip()
        role_id = str(job.get("standardRoleId") or "").strip()
        direct_term_ids = _as_id_list(job.get("technologyTermIds"))
        if direct_term_ids:
            direct_technology_job_ids.add(job_id)

        # De-duplicate all reachable technology nodes within one JD before R2 counts it.
        reachable_terms: dict[str, set[str]] = defaultdict(set)
        for term_id in direct_term_ids:
            term = technology_by_id.get(term_id)
            if term is None:
                warnings.add(f"job {job_id} references missing technology {term_id}")
                continue
            if str(term.get("level") or "") != "L4":
                warnings.add(
                    f"job {job_id} direct technology {term_id} is not L4; skipped"
                )
                continue

            path, missing_parent = _technology_path(term_id, technology_by_id)
            if missing_parent:
                warnings.add(
                    f"technology path from {term_id} stops at missing parent {missing_parent}"
                )

            for path_index, target_id in enumerate(path):
                reachable_terms[target_id].add(term_id)
                if path_index == 0:
                    continue  # Direct L4 facts stay in the fact layer, not R1.
                key = (job_id, target_id)
                r1_support_terms[key].add(term_id)
                candidate_path = path[: path_index + 1]
                if key not in r1_paths or candidate_path < r1_paths[key]:
                    r1_paths[key] = candidate_path

        if not role_id:
            continue
        for technology_id, support_terms in reachable_terms.items():
            key = (role_id, technology_id)
            r2_job_ids[key].add(job_id)
            if occ_id:
                r2_occ_ids[key].add(occ_id)
            r2_term_ids[key].update(support_terms)

    r1_relations: list[dict[str, Any]] = []
    for (job_id, technology_id), support_terms in sorted(r1_support_terms.items()):
        technology = technology_by_id[technology_id]
        source_job = job_by_id[job_id]
        occ_id = str(source_job.get("occId") or "").strip()
        r1_relations.append(
            {
                "id": _relation_id(RULE_TECH_HIERARCHY, job_id, technology_id),
                "relationType": "JD_TECH_INHERIT",
                "ruleId": RULE_TECH_HIERARCHY,
                "sourceId": job_id,
                "sourceOccId": occ_id,
                "targetId": technology_id,
                "targetName": str(technology.get("name") or ""),
                "targetLevel": str(technology.get("level") or ""),
                "supportCount": 1,
                "supportTermIds": sorted(support_terms),
                "evidenceJdIds": [job_id],
                "evidenceOccIds": [occ_id] if occ_id else [],
                "path": r1_paths[(job_id, technology_id)],
                "factOrDerived": "derived",
            }
        )

    r2_relations: list[dict[str, Any]] = []
    for (role_id, technology_id), evidence_job_ids in sorted(r2_job_ids.items()):
        technology = technology_by_id[technology_id]
        role = role_by_id.get(role_id, {})
        role_total = len(role_job_ids.get(role_id, set()))
        support_count = len(evidence_job_ids)
        level = str(technology.get("level") or "")
        r2_relations.append(
            {
                "id": _relation_id(RULE_ROLE_TECH, role_id, technology_id),
                "relationType": "STANDARD_ROLE_TECH_BY_JD",
                "ruleId": RULE_ROLE_TECH,
                "sourceId": role_id,
                "sourceName": str(role.get("name") or ""),
                "targetId": technology_id,
                "targetName": str(technology.get("name") or ""),
                "targetLevel": level,
                "supportCount": support_count,
                "roleJdCount": role_total,
                "coverage": round(support_count / role_total, 6) if role_total else None,
                "evidenceJdIds": sorted(evidence_job_ids),
                "evidenceOccIds": sorted(r2_occ_ids[(role_id, technology_id)]),
                "supportTermIds": sorted(r2_term_ids[(role_id, technology_id)]),
                "path": "standard_role <- JD -> technology",
                "inferenceBasis": "direct_l4" if level == "L4" else "r1_inherited",
                "factOrDerived": "derived",
            }
        )

    level_counts = Counter(relation["targetLevel"] for relation in r2_relations)
    graph_metadata = graph.get("metadata") if isinstance(graph.get("metadata"), Mapping) else {}
    return {
        "metadata": {
            "generatedAt": generated_at or datetime.now(UTC).isoformat(),
            "sourceGraphGeneratedAt": graph_metadata.get("generatedAt"),
            "sourceGraphSha256": source_sha256,
            "sourceJobCount": len(jobs),
            "sourceTechnologyNodeCount": len(raw_technologies),
            "uniqueTechnologyNodeCount": len(technology_by_id),
            "duplicateTechnologyRowCount": len(raw_technologies) - len(technology_by_id),
            "sourceStandardRoleCount": len(role_job_ids),
            "directTechnologyJobCount": len(direct_technology_job_ids),
            "r1RelationCount": len(r1_relations),
            "r2RelationCount": len(r2_relations),
            "r2LevelCounts": dict(
                sorted(level_counts.items(), key=lambda item: LEVEL_ORDER.get(item[0], 99))
            ),
            "warningCount": len(warnings),
            "warnings": sorted(warnings),
            "storagePolicy": (
                "fact relations remain unchanged; inferred relations are stored separately"
            ),
            "coverageNote": (
                "coverage is supporting JD count divided by all JDs assigned to the role; "
                "it is not accuracy"
            ),
        },
        "rules": [
            {
                "id": RULE_TECH_HIERARCHY,
                "name": "技术层级继承",
                "expression": "JD->L4 and L4->L3->L2->L1 implies JD->L3/L2/L1",
            },
            {
                "id": RULE_ROLE_TECH,
                "name": "标准岗位—技术多跳聚合",
                "expression": "standard_role<-JD->technology implies standard_role->technology",
            },
        ],
        "jdTechnologyInheritance": r1_relations,
        "standardRoleTechnologyRelations": r2_relations,
    }
