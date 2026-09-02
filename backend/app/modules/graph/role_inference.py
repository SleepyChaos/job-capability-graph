"""Explainable, non-destructive inference from JD facts to standard-role profiles.

This module deliberately writes a separate result set.  Existing Excel mappings are
kept as historical references and are never changed here.  Only assignments passing
the confidence gate are eligible for profile aggregation; uncertain records remain
candidates for review or new-role discovery.
"""

from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
import hashlib
import re
from typing import Any, Mapping, Sequence


DIMENSIONS = ("responsibilities", "skills", "abilities", "scenarios", "conditions")
WEIGHTS = {"title": 0.45, "duty": 0.25, "skill": 0.25, "category": 0.05}
GATES = {"confirmed": 0.74, "candidate": 0.55, "newRole": 0.32, "margin": 0.08}
GENERIC_TITLE_WORDS = (
    "高级", "资深", "初级", "中级", "首席", "助理", "工程师", "架构师", "设计师",
    "研究员", "科学家", "专家", "总监", "经理", "主管", "专员", "负责人", "顾问",
    "senior", "staff", "lead", "engineer", "manager", "director", "specialist",
)


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value: Any) -> str:
    value = _text(value).lower()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff+#.]+", "", value)


def _core_title(value: Any) -> str:
    result = _norm(value)
    for word in GENERIC_TITLE_WORDS:
        result = result.replace(word, "")
    return result


def _bigrams(value: Any) -> set[str]:
    value = _norm(value)
    if not value:
        return set()
    if len(value) == 1:
        return {value}
    return {value[index:index + 2] for index in range(len(value) - 1)}


def _similarity(left: Any, right: Any) -> float:
    a, b = _core_title(left), _core_title(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if min(len(a), len(b)) >= 3 and (a in b or b in a):
        return round(0.82 + 0.14 * min(len(a), len(b)) / max(len(a), len(b)), 6)
    pairs_a, pairs_b = _bigrams(a), _bigrams(b)
    jac = len(pairs_a & pairs_b) / max(1, len(pairs_a | pairs_b))
    return round(0.55 * jac + 0.45 * SequenceMatcher(None, a, b).ratio(), 6)


def _set_similarity(left: Sequence[str], right: Sequence[str]) -> tuple[float, list[str]]:
    a = {_norm(item) for item in left if _norm(item)}
    b = {_norm(item) for item in right if _norm(item)}
    shared = sorted(a & b)
    return (round(len(shared) / max(1, len(a | b)), 6), shared)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _tech_index(technical_inference: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation in technical_inference.get("jdTechnologyInheritance", []):
        if relation.get("targetLevel") != "L3":
            continue
        item = {
            "id": _text(relation.get("targetId")),
            "name": _text(relation.get("targetName")),
            "sourceL4Ids": list(relation.get("supportTermIds") or []),
            "path": list(relation.get("path") or []),
            "ruleId": _text(relation.get("ruleId")),
        }
        if item["id"]:
            result[_text(relation.get("sourceId"))].append(item)
    return result


def _point_records(job: Mapping[str, Any], l3_items: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Create point-level evidence. No point receives unrelated role-wide JD IDs."""
    profile = job.get("profile") if isinstance(job.get("profile"), Mapping) else {}
    jd_id, occ_id = _text(job.get("id")), _text(job.get("occId"))
    evidence_sentences = [_text(x) for x in profile.get("jdEvidence", []) if _text(x)]
    output: dict[str, list[dict[str, Any]]] = {dimension: [] for dimension in DIMENSIONS}

    for dimension in DIMENSIONS:
        for value in profile.get(dimension, []) or []:
            name = _text(value)
            if not name:
                continue
            snippets = [s for s in evidence_sentences if _norm(name) in _norm(s) or _similarity(name, s) >= 0.55][:2]
            output[dimension].append({
                "pointId": _stable_id("profile-point", dimension, _norm(name)),
                "name": name,
                "normalizedKey": _norm(name),
                "method": "single_jd_rule_extraction",
                "evidenceJdId": jd_id,
                "evidenceOccId": occ_id,
                "evidenceSnippets": snippets or evidence_sentences[:1],
            })

    existing_skill_keys = {item["normalizedKey"] for item in output["skills"]}
    for tech in l3_items:
        name, tech_id = _text(tech.get("name")), _text(tech.get("id"))
        key = f"technology:{tech_id}"
        if not tech_id or _norm(name) in existing_skill_keys:
            continue
        output["skills"].append({
            "pointId": key,
            "name": name,
            "normalizedKey": key,
            "method": "R1_L4_to_L3_technology_inheritance",
            "evidenceJdId": jd_id,
            "evidenceOccId": occ_id,
            "sourceL4Ids": list(tech.get("sourceL4Ids") or []),
            "technologyPath": list(tech.get("path") or []),
            "ruleId": _text(tech.get("ruleId")),
            "evidenceSnippets": [],
        })
    return output


def _build_reference_signatures(graph: Mapping[str, Any], tech_by_job: Mapping[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    signatures: dict[str, dict[str, Any]] = {}
    role_jobs: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for job in graph.get("jobs", []):
        role_id = _text(job.get("standardRoleId"))
        if role_id:
            role_jobs[role_id].append(job)
    for role in graph.get("standardRoles", []):
        role_id = _text(role.get("id"))
        jobs = role_jobs.get(role_id, [])
        job_features: list[dict[str, Any]] = []
        for job in jobs:
            profile = job.get("profile") or {}
            job_features.append({
                "jobId": _text(job.get("id")),
                "duties": [_text(x) for x in profile.get("responsibilities", []) if _text(x)],
                "skills": [_text(x) for x in profile.get("skills", []) if _text(x)],
                "technologyIds": [_text(x.get("id")) for x in tech_by_job.get(_text(job.get("id")), []) if _text(x.get("id"))],
            })
        signatures[role_id] = {
            "titles": list(dict.fromkeys([_text(role.get("name")), *(role.get("seedVariants") or [])])),
            "jobFeatures": job_features,
            "source": "legacy_mapping_reference",
        }
    return signatures


def infer_roles(graph: Mapping[str, Any], technical_inference: Mapping[str, Any]) -> dict[str, Any]:
    """Infer roles independently, preserving legacy mappings as reference only."""
    tech_by_job = _tech_index(technical_inference)
    signatures = _build_reference_signatures(graph, tech_by_job)
    roles = [role for role in graph.get("standardRoles", []) if _text(role.get("id"))]
    roles_by_cluster: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    clusters = {_text(item.get("id")): item for item in graph.get("clusters", [])}
    for role in roles:
        roles_by_cluster[_text(role.get("clusterId"))].append(role)

    results: list[dict[str, Any]] = []
    for job in graph.get("jobs", []):
        job_id = _text(job.get("id"))
        legacy_cluster = _text(job.get("clusterId"))
        l3_items = tech_by_job.get(job_id, [])
        job_profile = job.get("profile") or {}
        job_duties = [_text(x) for x in job_profile.get("responsibilities", []) if _text(x)]
        job_skills = [_text(x) for x in job_profile.get("skills", []) if _text(x)]
        job_tech_ids = {_text(x.get("id")) for x in l3_items if _text(x.get("id"))}

        # Candidate clusters: the historical cluster is a constrained search hint, not a final answer.
        cluster_scores: list[dict[str, Any]] = []
        for cluster_id, cluster in clusters.items():
            title_score = _similarity(job.get("title"), cluster.get("name"))
            reference_bonus = 0.18 if cluster_id == legacy_cluster else 0.0
            score = min(1.0, title_score * 0.82 + reference_bonus)
            cluster_scores.append({
                "clusterId": cluster_id,
                "clusterName": _text(cluster.get("name")),
                "score": round(score, 6),
                "evidence": (["历史Excel岗位簇仅用于缩小候选范围"] if reference_bonus else []) +
                            ([f"岗位标题与岗位簇名称相似度={title_score:.3f}"] if title_score else []),
            })
        cluster_candidates = sorted(cluster_scores, key=lambda x: (-x["score"], x["clusterId"]))[:3]
        best_cluster = clusters.get(cluster_candidates[0]["clusterId"], {}) if cluster_candidates else {}
        candidate_cluster_ids = {x["clusterId"] for x in cluster_candidates}
        candidate_roles = [role for cid in candidate_cluster_ids for role in roles_by_cluster.get(cid, [])]

        ranked_roles: list[dict[str, Any]] = []
        for role in candidate_roles:
            role_id = _text(role.get("id"))
            signature = signatures.get(role_id, {})
            # Leave-one-out prevents a historical assignment from proving itself.
            peer_features = [x for x in signature.get("jobFeatures", []) if x.get("jobId") != job_id]
            reference_duties = list(dict.fromkeys(d for x in peer_features for d in x.get("duties", [])))[:16]
            reference_skills = list(dict.fromkeys(s for x in peer_features for s in x.get("skills", [])))[:32]
            reference_tech_ids = {t for x in peer_features for t in x.get("technologyIds", [])}
            title_score = max((_similarity(job.get("title"), title) for title in signature.get("titles", [])), default=0.0)
            duty_score = max((_similarity(duty, ref) for duty in job_duties for ref in reference_duties), default=0.0)
            skill_text_score, shared_skills = _set_similarity(job_skills, reference_skills)
            shared_tech = sorted(job_tech_ids & reference_tech_ids)
            tech_score = len(shared_tech) / max(1, len(job_tech_ids | reference_tech_ids))
            skill_score = max(skill_text_score, tech_score)
            category_score = 1.0 if _text(role.get("categoryName")) == _text(best_cluster.get("categoryName")) else 0.0
            total = sum((title_score, duty_score, skill_score, category_score)[i] * weight for i, weight in enumerate(WEIGHTS.values()))
            channels = sum(x >= 0.12 for x in (title_score, duty_score, skill_score)) + int(category_score > 0)
            ranked_roles.append({
                "roleId": role_id,
                "roleName": _text(role.get("name")),
                "clusterId": _text(role.get("clusterId")),
                "score": round(total, 6),
                "componentScores": {"title": round(title_score, 6), "duty": round(duty_score, 6), "skill": round(skill_score, 6), "category": category_score},
                "evidenceChannels": channels,
                "evidence": {
                    "matchedSkills": shared_skills[:8],
                    "matchedL3TechnologyIds": shared_tech[:12],
                    "basis": "岗位标题+JD职责+技能/技术+职业类别约束",
                    "referenceNotice": "岗位原型来自历史映射，仅作为候选比较基线",
                },
            })
        ranked_roles.sort(key=lambda x: (-x["score"], x["roleId"]))
        best = ranked_roles[0] if ranked_roles else None
        second_score = ranked_roles[1]["score"] if len(ranked_roles) > 1 else 0.0
        margin = round((best["score"] if best else 0.0) - second_score, 6)
        if not best or best["score"] < GATES["newRole"]:
            status = "new_role_candidate"
        elif best["score"] >= GATES["confirmed"] and margin >= GATES["margin"] and best["evidenceChannels"] >= 2:
            status = "confirmed"
        elif best["score"] >= GATES["candidate"] and best["evidenceChannels"] >= 2:
            status = "candidate"
        else:
            status = "review_required"

        point_records = _point_records(job, l3_items)
        results.append({
            "jdId": job_id,
            "occId": _text(job.get("occId")),
            "title": _text(job.get("title")),
            "legacyMapping": {
                "directionId": _text(job.get("directionId")), "directionName": _text(job.get("directionName")),
                "categoryId": _text(job.get("categoryId")), "categoryName": _text(job.get("categoryName")),
                "clusterId": legacy_cluster, "clusterName": _text(job.get("clusterName")),
                "standardRoleId": _text(job.get("standardRoleId")), "standardRoleName": _text(job.get("standardRoleName")),
                "method": _text(job.get("standardRoleMappingMethod")), "confidence": job.get("standardRoleMappingConfidence"),
                "source": "historical_excel_reference",
            },
            "careerDirection": {
                "resultId": _text(best_cluster.get("directionId")),
                "result": _text(best_cluster.get("directionName")),
                "score": cluster_candidates[0]["score"] if cluster_candidates else 0.0,
                "method": "由候选岗位簇的上位层级推导",
                "evidence": cluster_candidates[0]["evidence"] if cluster_candidates else [],
            },
            "careerCategory": {
                "resultId": _text(best_cluster.get("categoryId")),
                "result": _text(best_cluster.get("categoryName")),
                "score": cluster_candidates[0]["score"] if cluster_candidates else 0.0,
                "method": "由候选岗位簇的上位层级推导",
                "evidence": cluster_candidates[0]["evidence"] if cluster_candidates else [],
            },
            "clusterCandidates": cluster_candidates,
            "standardRole": {"result": best, "alternatives": ranked_roles[1:3], "margin": margin, "status": status,
                             "reason": "仅通过置信闸门的结果可进入正式关系；其余保留候选或人工审核。"},
            "publishable": status == "confirmed",
            "profileExtraction": point_records,
        })

    profiles = aggregate_confirmed_profiles(results)
    status_counts: dict[str, int] = defaultdict(int)
    for item in results:
        status_counts[item["standardRole"]["status"]] += 1
    return {
        "metadata": {
            "resultType": "independent_role_inference",
            "nonDestructive": True,
            "legacyMappingUsage": "reference_only",
            "weights": WEIGHTS,
            "gates": GATES,
            "profilePolicy": "single-JD evidence aggregation; no role-wide evidence copying",
        },
        "audit": {"jobCount": len(results), "statusDistribution": dict(status_counts), "confirmedProfileCount": len(profiles)},
        "jobRoleInferences": results,
        "standardRoleProfiles": profiles,
    }


def aggregate_confirmed_profiles(results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in results:
        role = item.get("standardRole", {})
        result = role.get("result") if isinstance(role, Mapping) else None
        if role.get("status") == "confirmed" and isinstance(result, Mapping) and result.get("roleId"):
            grouped[_text(result.get("roleId"))].append(item)

    profiles: list[dict[str, Any]] = []
    for role_id, jobs in sorted(grouped.items()):
        dimensions: dict[str, list[dict[str, Any]]] = {}
        for dimension in DIMENSIONS:
            points: dict[str, dict[str, Any]] = {}
            for job in jobs:
                seen_in_job: set[str] = set()
                for point in job.get("profileExtraction", {}).get(dimension, []):
                    key = _text(point.get("normalizedKey"))
                    if not key or key in seen_in_job:
                        continue
                    seen_in_job.add(key)
                    record = points.setdefault(key, {"name": _text(point.get("name")), "supportJdIds": [], "supportOccIds": [], "evidenceSnippets": [], "methods": set()})
                    record["supportJdIds"].append(_text(job.get("jdId")))
                    if _text(job.get("occId")):
                        record["supportOccIds"].append(_text(job.get("occId")))
                    record["evidenceSnippets"].extend(point.get("evidenceSnippets") or [])
                    record["methods"].add(_text(point.get("method")))
            published, candidates = [], []
            for key, record in points.items():
                support_ids = sorted(set(record["supportJdIds"]))
                item = {
                    "pointId": _stable_id("role-profile", role_id, dimension, key),
                    "name": record["name"],
                    "supportCount": len(support_ids),
                    "coverage": round(len(support_ids) / len(jobs), 6),
                    "evidenceJdIds": support_ids,
                    "evidenceOccIds": sorted(set(record["supportOccIds"])),
                    "evidenceSnippets": list(dict.fromkeys(record["evidenceSnippets"]))[:5],
                    "methods": sorted(x for x in record["methods"] if x),
                }
                (published if item["supportCount"] >= 2 else candidates).append(item)
            dimensions[dimension] = sorted(published, key=lambda x: (-x["supportCount"], x["name"]))
            dimensions[f"{dimension}Candidates"] = sorted(candidates, key=lambda x: x["name"])
        first_role = jobs[0]["standardRole"]["result"]
        profiles.append({"standardRoleId": role_id, "standardRoleName": first_role["roleName"], "confirmedJdCount": len(jobs), "dimensions": dimensions})
    return profiles
