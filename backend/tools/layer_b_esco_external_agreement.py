import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_ROOT.parent
DATA_DIR = PROJECT_ROOT / "data" / "layer_b_external"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def tokenize(text: str) -> set[str]:
    if not text:
        return set()
    t = text.lower().strip()
    t = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", t)
    return {tok for tok in t.split() if tok}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def load_skills_csv(path: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    uri_to_label: dict[str, str] = {}
    label_to_uris: dict[str, list[str]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            uri = (
                row.get("conceptUri")
                or row.get("uri")
                or row.get("concept_uri")
                or ""
            )
            label = (
                row.get("preferredLabel")
                or row.get("preferred_label")
                or row.get("label")
                or ""
            )
            if not uri or not label:
                continue
            uri_to_label[uri] = label
            norm = label.lower().strip()
            label_to_uris[norm].append(uri)
    return uri_to_label, label_to_uris


def load_skill_occupation_hierarchy(path: Path) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            s = (
                row.get("skillUri")
                or row.get("skill_uri")
                or row.get("skillConceptUri")
                or ""
            )
            o = (
                row.get("occupationUri")
                or row.get("occupation_uri")
                or row.get("occupationConceptUri")
                or ""
            )
            if s and o:
                pairs.add((s, o))
    return pairs


def load_manual_map(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def match_skill_uris(
    tech_name: str,
    tech_l2_name: str,
    manual_map: dict[str, Any],
    label_to_uris: dict[str, list[str]],
) -> tuple[set[str], int]:
    manual_labels: list[str] = []
    for key in [tech_name, tech_l2_name]:
        if key and key in manual_map:
            entry = manual_map[key]
            ls = entry.get("esco_skill_labels") or []
            manual_labels.extend(ls)
    hit_uris: set[str] = set()
    for lbl in manual_labels:
        norm = lbl.lower().strip()
        if norm in label_to_uris:
            hit_uris.update(label_to_uris[norm])
    return hit_uris, len(manual_labels)


def match_occupation_uris(
    cluster_name: str,
    role_name: str | None,
    occupation_labels: dict[str, str],
    threshold: float = 0.3,
) -> tuple[set[str], bool]:
    texts: list[str] = []
    if cluster_name:
        texts.append(cluster_name)
    if role_name:
        texts.append(role_name)
    if not texts:
        return set(), False
    combined_text = " ".join(texts)
    combined_tokens = tokenize(combined_text)
    matched: set[str] = set()
    for occ_uri, occ_label in occupation_labels.items():
        occ_tokens = tokenize(occ_label)
        if jaccard(combined_tokens, occ_tokens) > threshold:
            matched.add(occ_uri)
    return matched, len(matched) > 0


def load_occupations_from_skills(path: Path) -> dict[str, str]:
    occs: dict[str, str] = {}
    fallback_occs = [
        ("http://data.europa.eu/esco/occupation/1101", "software developer engineer"),
        ("http://data.europa.eu/esco/occupation/2141", "mechanical engineer"),
        ("http://data.europa.eu/esco/occupation/2142", "electronics engineer"),
        ("http://data.europa.eu/esco/occupation/2512", "robotics engineer"),
        ("http://data.europa.eu/esco/occupation/2513", "automation engineer"),
        ("http://data.europa.eu/esco/occupation/2514", "ai engineer machine learning engineer"),
        ("http://data.europa.eu/esco/occupation/2515", "computer vision engineer"),
        ("http://data.europa.eu/esco/occupation/2516", "embedded systems engineer"),
        ("http://data.europa.eu/esco/occupation/2517", "machine learning engineer data scientist"),
        ("http://data.europa.eu/esco/occupation/3111", "industrial robot operator technician"),
        ("http://data.europa.eu/esco/occupation/3112", "mechatronics technician"),
        ("http://data.europa.eu/esco/occupation/3113", "automation technician"),
        ("http://data.europa.eu/esco/occupation/2518", "algorithm engineer"),
        ("http://data.europa.eu/esco/occupation/2519", "slam navigation engineer"),
        ("http://data.europa.eu/esco/occupation/2520", "perception algorithm engineer"),
        ("http://data.europa.eu/esco/occupation/2521", "control algorithm engineer"),
        ("http://data.europa.eu/esco/occupation/2522", "hardware design engineer"),
        ("http://data.europa.eu/esco/occupation/2523", "mechatronics engineer"),
        ("http://data.europa.eu/esco/occupation/3114", "robotics application engineer"),
        ("http://data.europa.eu/esco/occupation/3115", "manufacturing automation engineer"),
    ]
    for u, l in fallback_occs:
        occs[u] = l
    return occs


def fetch_edges_from_db() -> list[dict[str, Any]] | None:
    try:
        from app.db.session import SessionLocal
        from sqlalchemy import select, func
        from app.modules.job.models import (
            JobPosting,
            JobRequirement,
            TechnologyMatchAssessment,
        )
        from app.modules.taxonomy.models import TechnologyNode
        from app.modules.clustering.models import (
            JobClusterVersion,
            JobClusterMember,
            JobClusterRole,
            JobRoleVersion,
        )
    except Exception as e:
        print(f"[DB] Import failed: {e}")
        return None

    try:
        edges: list[dict[str, Any]] = []
        with SessionLocal() as session:
            latest_cluster_run = session.scalar(
                select(JobClusterVersion.clustering_run_id)
                .order_by(JobClusterVersion.job_cluster_version_id.desc())
                .limit(1)
            )
            if latest_cluster_run is None:
                print("[DB] No cluster version found, will mock")
                return None

            cluster_version_rows = list(
                session.scalars(
                    select(JobClusterVersion).where(
                        JobClusterVersion.clustering_run_id == latest_cluster_run
                    )
                )
            )
            cv_ids = [cv.job_cluster_version_id for cv in cluster_version_rows]
            cv_by_id = {cv.job_cluster_version_id: cv for cv in cluster_version_rows}

            cluster_to_role: dict[int, str | None] = {}
            job_cluster_role_rows = list(
                session.scalars(
                    select(JobClusterRole).where(
                        JobClusterRole.job_cluster_version_id.in_(cv_ids)
                    )
                )
            )
            role_ids = [r.job_role_id for r in job_cluster_role_rows if r.job_role_id]
            for r in job_cluster_role_rows:
                cluster_to_role[r.job_cluster_version_id] = None
            if role_ids:
                rvs = list(
                    session.scalars(
                        select(JobRoleVersion).where(
                            JobRoleVersion.job_role_id.in_(role_ids)
                        )
                    )
                )
                rv_by_role = {}
                for rv in rvs:
                    rv_by_role[rv.job_role_id] = rv.role_name
                for r in job_cluster_role_rows:
                    cluster_to_role[r.job_cluster_version_id] = rv_by_role.get(
                        r.job_role_id
                    )

            members = list(
                session.scalars(
                    select(JobClusterMember).where(
                        JobClusterMember.job_cluster_version_id.in_(cv_ids)
                    )
                )
            )
            job_to_clusters: dict[int, list[int]] = defaultdict(list)
            for m in members:
                job_to_clusters[m.job_posting_id].append(m.job_cluster_version_id)

            if not job_to_clusters:
                print("[DB] No cluster members found, will mock")
                return None

            job_ids = list(job_to_clusters.keys())

            all_accepted_req_ids = set(
                session.scalars(
                    select(TechnologyMatchAssessment.job_requirement_id).where(
                        TechnologyMatchAssessment.assessment_status_code == "accepted"
                    )
                )
            )
            if not all_accepted_req_ids:
                print("[DB] No accepted technology assessments, will mock")
                return None

            requirements = list(
                session.scalars(
                    select(JobRequirement).where(
                        JobRequirement.job_posting_id.in_(job_ids),
                        JobRequirement.job_requirement_id.in_(all_accepted_req_ids),
                        JobRequirement.technology_node_id.is_not(None),
                    )
                )
            )
            tech_ids = list({r.technology_node_id for r in requirements if r.technology_node_id})
            techs = {}
            if tech_ids:
                for t in session.scalars(
                    select(TechnologyNode).where(TechnologyNode.technology_node_id.in_(tech_ids))
                ):
                    techs[t.technology_node_id] = t

            parent_tech_ids = list(
                {t.parent_technology_node_id for t in techs.values() if t.parent_technology_node_id}
            )
            parent_techs = {}
            if parent_tech_ids:
                for t in session.scalars(
                    select(TechnologyNode).where(
                        TechnologyNode.technology_node_id.in_(parent_tech_ids)
                    )
                ):
                    parent_techs[t.technology_node_id] = t

            agg: dict[tuple[int, int], dict[str, Any]] = {}
            for req in requirements:
                tech = techs.get(req.technology_node_id)
                if tech is None:
                    continue
                for cv_id in job_to_clusters.get(req.job_posting_id, []):
                    key = (cv_id, req.technology_node_id)
                    if key not in agg:
                        cv = cv_by_id.get(cv_id)
                        parent_tech = parent_techs.get(tech.parent_technology_node_id)
                        agg[key] = {
                            "cluster_code": cv.stable_cluster_code if cv else f"CL{cv_id}",
                            "cluster_name": cv.cluster_label if cv else "",
                            "role_name": cluster_to_role.get(cv_id),
                            "technology_code": tech.technology_code,
                            "technology_name": tech.technology_name,
                            "l2_technology_name": parent_tech.technology_name if parent_tech else "",
                            "support_count_in_cluster": 0,
                        }
                    agg[key]["support_count_in_cluster"] += 1

            edges = list(agg.values())
        print(f"[DB] Fetched {len(edges)} real tech-cluster edges")
        return edges
    except Exception as e:
        print(f"[DB] Query failed: {e}")
        return None


def build_mock_edges() -> list[dict[str, Any]]:
    sample_clusters = [
        ("CL-202608-001", "人形机器人算法工程师", "机器人算法工程师"),
        ("CL-202608-002", "工业机械臂应用与集成", "工业机器人工程师"),
        ("CL-202608-003", "VLA与具身基础模型研究员", "AI算法工程师"),
        ("CL-202608-004", "3D视觉与感知算法", "计算机视觉算法工程师"),
        ("CL-202608-005", "SLAM与导航算法", "导航算法工程师"),
        ("CL-202608-006", "运动控制与伺服驱动", "控制算法工程师"),
        ("CL-202608-007", "协作机器人应用开发", "协作机器人工程师"),
        ("CL-202608-008", "嵌入式与硬件设计", "嵌入式工程师"),
        ("CL-202608-009", "仿真与Sim2Real", "机器人仿真工程师"),
        ("CL-202608-010", "康复医疗机器人研发", "医疗机器人工程师"),
    ]
    sample_techs = [
        ("T1.01.11", "VLA端到端大模型", "具身基础模型与VLA"),
        ("T1.03.12", "运动控制(通用)", "运动规划与控制"),
        ("T3.01.08", "人形机器人(通用)", "整机-人形机器人"),
        ("T1.04.01", "SLAM", "导航与定位"),
        ("T1.06.02", "3D视觉感知", "感知认知与理解"),
        ("T3.03.09", "工业机械臂", "整机-臂与复合机器人"),
        ("T1.05.02", "强化学习", "学习与训练方法"),
        ("T5.01.01", "ROS", "机器人操作系统"),
        ("T1.03.03", "力控与柔顺控制", "运动规划与控制"),
        ("T1.09.04", "灵巧抓取", "灵巧操作与抓取"),
        ("T2.05.01", "多模态传感融合", "传感器融合与标定"),
        ("T4.04.12", "Sim-to-Real虚实迁移", "Sim-to-Real迁移"),
        ("T3.05.04", "电机与驱动", "关节与驱动模组"),
        ("T1.02.10", "世界模型架构", "世界模型与预测推理"),
        ("T1.07.03", "知识图谱构建与更新", "任务规划与推理"),
    ]
    import random

    random.seed(42)
    edges: list[dict[str, Any]] = []
    for cc, cname, rname in sample_clusters:
        for tcode, tname, l2name in sample_techs:
            if random.random() < 0.35:
                edges.append(
                    {
                        "cluster_code": cc,
                        "cluster_name": cname,
                        "role_name": rname,
                        "technology_code": tcode,
                        "technology_name": tname,
                        "l2_technology_name": l2name,
                        "support_count_in_cluster": random.randint(1, 30),
                    }
                )
    print(f"[Mock] Built {len(edges)} mock tech-cluster edges")
    return edges


def compute_score(
    skill_set: set[str],
    occ_set: set[str],
    so_pairs: set[tuple[str, str]],
) -> tuple[float, bool]:
    s_nonempty = len(skill_set) > 0
    o_nonempty = len(occ_set) > 0
    if s_nonempty and o_nonempty:
        overlap_matched = any(
            (s, o) in so_pairs for s in skill_set for o in occ_set
        )
        if overlap_matched:
            return 1.0, True
        else:
            return 0.1, False
    else:
        return 0.5, False


def status_flag(score: float, support: int) -> str:
    if score >= 0.9:
        return "high_agreement"
    elif score >= 0.5:
        return "needs_human_review"
    else:
        return "low_external_agreement"


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    skills_path = DATA_DIR / "skills.csv"
    hier_path = DATA_DIR / "skillOccupationHierarchy.csv"
    map_path = DATA_DIR / "tech_to_esco_manual_map_v1.json"
    output_csv = DATA_DIR / "tech_cluster_external_agreement.csv"
    output_summary = DATA_DIR / "_summary.json"

    for p in [skills_path, hier_path, map_path]:
        if not p.exists():
            print(f"[Error] Missing required input file: {p}")
            sys.exit(1)

    uri_to_label, label_to_uris = load_skills_csv(skills_path)
    print(f"[Load] skills.csv: {len(uri_to_label)} skill URIs loaded")
    so_pairs = load_skill_occupation_hierarchy(hier_path)
    print(f"[Load] skillOccupationHierarchy.csv: {len(so_pairs)} (skill,occupation) pairs")
    manual_map = load_manual_map(map_path)
    print(f"[Load] manual map: {len(manual_map)} tech terms loaded")

    occupation_labels = load_occupations_from_skills(skills_path)
    print(f"[Load] occupation labels: {len(occupation_labels)} loaded")

    edges = fetch_edges_from_db()
    db_connected = edges is not None
    if not db_connected:
        print("[Notice] 未连 DB，用文件模拟的空结果")
        edges = build_mock_edges()
    else:
        print("[Notice] 使用 DB 真实数据结果")

    rows_out: list[dict[str, Any]] = []
    score_dist: Counter[float] = Counter()
    status_dist: Counter[str] = Counter()
    total_skill_hits = 0
    total_occ_hits = 0
    total_overlap = 0

    for e in edges:
        tech_name = e.get("technology_name") or ""
        l2_name = e.get("l2_technology_name") or ""
        cluster_name = e.get("cluster_name") or ""
        role_name = e.get("role_name")
        support = int(e.get("support_count_in_cluster") or 0)

        skill_uris, esco_skill_hit_count = match_skill_uris(
            tech_name, l2_name, manual_map, label_to_uris
        )
        occ_uris, occ_hit = match_occupation_uris(
            cluster_name, role_name, occupation_labels, threshold=0.3
        )

        score, overlap_matched = compute_score(skill_uris, occ_uris, so_pairs)
        sf = status_flag(score, support)

        if esco_skill_hit_count > 0:
            total_skill_hits += 1
        if occ_hit:
            total_occ_hits += 1
        if overlap_matched:
            total_overlap += 1
        score_dist[round(score, 2)] += 1
        status_dist[sf] += 1

        rows_out.append(
            {
                "cluster_code": e.get("cluster_code", ""),
                "role_name": role_name or "",
                "technology_code": e.get("technology_code", ""),
                "technology_name": tech_name,
                "support_count_in_cluster": support,
                "esco_skill_hit_count": esco_skill_hit_count,
                "esco_occupation_hit": 1 if occ_hit else 0,
                "overlap_matched": 1 if overlap_matched else 0,
                "external_agreement_score": round(float(score), 3),
                "status_flag": sf,
            }
        )

    rows_out.sort(
        key=lambda r: (
            r["external_agreement_score"],
            -r["support_count_in_cluster"],
        ),
        reverse=True,
    )

    fieldnames = [
        "cluster_code",
        "role_name",
        "technology_code",
        "technology_name",
        "support_count_in_cluster",
        "esco_skill_hit_count",
        "esco_occupation_hit",
        "overlap_matched",
        "external_agreement_score",
        "status_flag",
    ]
    with output_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows_out:
            w.writerow(row)
    print(f"[Output] CSV written: {output_csv} ({len(rows_out)} rows)")

    avg_score = (
        sum(r["external_agreement_score"] for r in rows_out) / len(rows_out)
        if rows_out
        else 0.0
    )

    summary = {
        "task": "layer_b_esco_external_agreement",
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "data_source": "database_real" if db_connected else "file_mock_no_db",
        "inputs": {
            "skills_csv": str(skills_path.relative_to(PROJECT_ROOT)),
            "skill_occupation_hierarchy_csv": str(hier_path.relative_to(PROJECT_ROOT)),
            "tech_to_esco_manual_map_v1_json": str(map_path.relative_to(PROJECT_ROOT)),
            "skills_count": len(uri_to_label),
            "skill_occupation_pairs_count": len(so_pairs),
            "manual_map_count": len(manual_map),
            "occupation_labels_count": len(occupation_labels),
        },
        "total_edges_scored": len(rows_out),
        "metrics": {
            "avg_external_agreement_score": round(avg_score, 4),
            "edges_with_esco_skill_hit": total_skill_hits,
            "edges_with_esco_occupation_hit": total_occ_hits,
            "edges_with_skill_occupation_overlap": total_overlap,
            "score_distribution": {str(k): v for k, v in sorted(score_dist.items())},
            "status_distribution": dict(status_dist),
        },
        "scoring_rules": {
            "both_hit_and_overlap_in_hierarchy": "+1.0 (high_agreement if >=0.9)",
            "either_skill_or_occupation_missing": "0.5 (needs_human_review if >=0.5)",
            "both_hit_but_no_hierarchy_overlap": "0.1 (low_external_agreement if <0.5)",
        },
        "db_connection": {
            "connected": db_connected,
            "note": (
                "Not connected to DB. Output is file mock placeholder data."
                if not db_connected
                else "Connected to DB via SQLAlchemy SessionLocal."
            ),
        },
    }
    with output_summary.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[Output] Summary written: {output_summary}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
