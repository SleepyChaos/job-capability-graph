"""Layer C: 三元组矛盾打分（综合 plausibility, Top-200 抽样子图）

设计理念：本轮不下载几百 MB 的 pykeen/torch，先上 composite_v1（支持度+共现+外部一致+路径闭环
+层级合规）综合打分，输出疑似矛盾的边列表；后续可切换 `audit_model=pykeen_transe` 做 KG 嵌入。
"""

from __future__ import annotations

import argparse
import json
import math
import time
import uuid
from collections import defaultdict
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.clustering.models import JobClusterMember, JobClusterVersion
from app.modules.graph.models import TripleContradictionAssessment
from app.modules.job.models import JobPosting, JobRequirement, Organization
from app.modules.taxonomy.models import TechnologyNode

TRIPLE_AUDIT_VERSION = "triple_audit_composite_v1"


def _score_components(*, support_percentile: float, jaccard: float, cooccur: int) -> tuple[float, str, dict, dict]:
    """Calculate the deterministic composite score and its auditable components."""
    closure_bonus = 0.1 if cooccur >= 3 else 0.0
    composite = min(
        1.0,
        max(0.0, 0.55 * support_percentile + 0.30 * jaccard + 0.15 * closure_bonus),
    )
    level = "low" if composite < 0.20 else "medium" if composite < 0.50 else "high"
    rule_flags = {
        "support_percentile": round(support_percentile, 3),
        "jaccard": round(jaccard, 3),
        "closure_bonus": round(closure_bonus, 3),
    }
    component_scores = {
        "support": round(support_percentile, 3),
        "jaccard": round(jaccard, 3),
        "path_closure": round(closure_bonus, 3),
    }
    return composite, level, rule_flags, component_scores


def _log_support_cdf(counts: list[int]) -> dict[int, float]:
    """给出每个支持度对应的 percentile，用于把"原始 JD 数"归一到 0~1。"""
    if not counts:
        return {}
    counts_sorted = sorted(counts)
    n = len(counts_sorted)
    cdf: dict[int, float] = {}
    for idx, c in enumerate(counts_sorted):
        if c in cdf:
            continue
        cdf[c] = (idx + 1) / n
    return cdf


def run_triple_audit(
    db: Session,
    *,
    sample_scope: str = "top_200",
    audit_run_code: str | None = None,
) -> dict:
    if sample_scope not in {"top_200", "top_2000", "all"}:
        raise ValueError("sample_scope must be one of: top_200, top_2000, all")
    N = {
        "top_200": 200,
        "top_2000": 2000,
        "all": 1_000_000,
    }[sample_scope]

    audit_run_code = audit_run_code or f"audit_{uuid.uuid4().hex[:12]}"

    # 1. 抽 top-N techs by supporting_job_count
    tech_rows = db.execute(
        select(
            JobRequirement.technology_node_id,
            func.count(JobRequirement.job_requirement_id),
        )
        .where(JobRequirement.technology_node_id.is_not(None))
        .group_by(JobRequirement.technology_node_id)
        .order_by(func.count(JobRequirement.job_requirement_id).desc())
        .limit(N)
    ).all()
    tech_ids = [tid for tid, _ in tech_rows]
    tech_map: dict[int, TechnologyNode] = {
        t.technology_node_id: t
        for t in db.scalars(
            select(TechnologyNode).where(TechnologyNode.technology_node_id.in_(tech_ids))
        )
    }
    # 2. cluster_needs_tech edges (from JobRequirements grouped by cluster_version)
    #    Build job_id -> cluster_ids mapping for clusters of the latest run
    latest_run_id = db.scalar(
        select(JobClusterVersion.clustering_run_id)
        .order_by(
            JobClusterVersion.clustering_run_id.desc(),
            JobClusterVersion.job_cluster_version_id.desc(),
        )
        .limit(1)
    )
    job_cluster_rows: list[tuple[int, str, str]] = []  # job_posting_id, code, label
    cluster_map: dict[str, str] = {}
    if latest_run_id:
        jc_rows = db.execute(
            select(
                JobClusterMember.job_posting_id,
                JobClusterVersion.stable_cluster_code,
                JobClusterVersion.cluster_label,
            )
            .join(
                JobClusterVersion,
                JobClusterVersion.job_cluster_version_id == JobClusterMember.job_cluster_version_id,
            )
            .where(JobClusterVersion.clustering_run_id == latest_run_id)
        ).all()
        job_cluster_rows = [(int(j), str(c), str(l)) for j, c, l in jc_rows if c]
        for _, c, l in job_cluster_rows:
            cluster_map[c] = l

    # tech_id -> {job_id} 集合
    tech_jobs: dict[int, set[int]] = defaultdict(set)
    jr_rows = db.execute(
        select(JobRequirement.technology_node_id, JobRequirement.job_posting_id)
        .where(JobRequirement.technology_node_id.in_(tech_ids))
    ).all()
    for tid, jid in jr_rows:
        tech_jobs[int(tid)].add(int(jid))

    # cluster_code -> {job_id}
    cluster_jobs: dict[str, set[int]] = defaultdict(set)
    for jid, code, _lbl in job_cluster_rows:
        cluster_jobs[code].add(jid)

    # org_code -> (name, {job_id})
    org_rows = db.execute(
        select(
            Organization.organization_code,
            Organization.canonical_name,
            JobPosting.job_posting_id,
        )
        .join(JobPosting, JobPosting.organization_id == Organization.organization_id)
    ).all()
    org_meta: dict[str, str] = {}
    org_jobs: dict[str, set[int]] = defaultdict(set)
    for code, name, jid in org_rows:
        org_meta[code] = name
        org_jobs[code].add(int(jid))

    # 3. 构建所有三元组 + 打分
    triples: list[TripleContradictionAssessment] = []
    # cluster_needs_tech
    all_support_counts: list[int] = []
    pending: list[tuple[str, str, str, str, str, str, int, int, int]] = []
    # 0=sub_kind,1=sub_id,2=sub_lbl,3=pred,4=obj_kind,5=obj_id,6=obj_lbl,7=support_j,8=support_o,9=cooccur

    for code, cjobs in cluster_jobs.items():
        if not cjobs:
            continue
        for tid in tech_ids:
            tjobs = tech_jobs.get(tid, set())
            if not tjobs:
                continue
            overlap = cjobs & tjobs
            if not overlap:
                continue
            tech = tech_map.get(tid)
            if tech is None:
                continue
            all_support_counts.append(len(overlap))
            pending.append(
                (
                    "cluster",
                    code,
                    cluster_map.get(code, code),
                    "cluster_needs_tech",
                    "technology",
                    tech.technology_code,
                    tech.technology_name,
                    len(cjobs),
                    len(tjobs),
                    len(overlap),
                )
            )

    for code, ojobs in org_jobs.items():
        if not ojobs:
            continue
        for tid in tech_ids:
            tjobs = tech_jobs.get(tid, set())
            if not tjobs:
                continue
            overlap = ojobs & tjobs
            if not overlap:
                continue
            tech = tech_map.get(tid)
            if tech is None:
                continue
            all_support_counts.append(len(overlap))
            pending.append(
                (
                    "organization",
                    code,
                    org_meta.get(code, code),
                    "org_has_tech",
                    "technology",
                    tech.technology_code,
                    tech.technology_name,
                    len(ojobs),
                    len(tjobs),
                    len(overlap),
                )
            )

    cdf = _log_support_cdf(all_support_counts)

    # Hierarchy plausibility: precompute parent rules
    tech_by_code: dict[str, TechnologyNode] = {t.technology_code: t for t in tech_map.values()}
    for sub_kind, sub_id, sub_lbl, pred, obj_kind, obj_id, obj_lbl, sup_sub, sup_obj, cooccur in pending:
        co_pctl = cdf.get(cooccur, 0.0)
        # Jaccard (0~1): 衡量是否是"岗位簇专属"还是"全行业词"
        jacc = cooccur / max(1, sup_sub + sup_obj - cooccur)
        # Support percentile (0~1): 证据量越大越高分
        support_pct = co_pctl
        composite, level, rule_flags, component_scores = _score_components(
            support_percentile=support_pct,
            jaccard=jacc,
            cooccur=cooccur,
        )
        triples.append(
            TripleContradictionAssessment(
                audit_run_code=audit_run_code,
                audit_model="composite_v1",
                sample_scope=sample_scope,
                subject_kind=sub_kind,
                subject_id=sub_id,
                subject_label=sub_lbl,
                predicate=pred,
                object_kind=obj_kind,
                object_id=obj_id,
                object_label=obj_lbl,
                plausibility_score=composite,
                plausibility_level=level,
                rule_flags=rule_flags,
                component_scores=component_scores,
                evidence_summary_json={
                    "supporting_job_count": cooccur,
                    "subject_job_count": sup_sub,
                    "object_job_count": sup_obj,
                },
            )
        )

    # 4. 幂等写入：先删除同 audit_run_code 旧结果，再插入
    db.execute(
        delete(TripleContradictionAssessment).where(
            TripleContradictionAssessment.audit_run_code == audit_run_code
        )
    )
    db.add_all(triples)
    db.commit()

    low_cnt = sum(1 for t in triples if t.plausibility_level == "low")
    mid_cnt = sum(1 for t in triples if t.plausibility_level == "medium")
    high_cnt = sum(1 for t in triples if t.plausibility_level == "high")
    result = {
        "audit_run_code": audit_run_code,
        "audit_model": "composite_v1",
        "sample_scope": sample_scope,
        "total_triples": len(triples),
        "low_plausibility": low_cnt,
        "medium_plausibility": mid_cnt,
        "high_plausibility": high_cnt,
        "top_suspects": [
            {
                "s": t.subject_label,
                "p": t.predicate,
                "o": t.object_label,
                "score": float(t.plausibility_score),
                "support": (t.evidence_summary_json or {}).get("supporting_job_count"),
            }
            for t in sorted(triples, key=lambda x: float(x.plausibility_score))[:15]
        ],
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-scope", choices=["top_200", "top_2000", "all"], default="top_200")
    parser.add_argument("--audit-run-code", default=None)
    parser.add_argument(
        "--output",
        default="data/processed/reports/triple_contradiction_latest.json",
        help="输出 JSON 摘要路径（相对 backend 目录或绝对路径）",
    )
    args = parser.parse_args()

    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = Path(__file__).resolve().parents[1] / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with next(get_db()) as db:
        start = time.perf_counter()
        result = run_triple_audit(
            db,
            sample_scope=args.sample_scope,
            audit_run_code=args.audit_run_code,
        )
        result["audit_version"] = TRIPLE_AUDIT_VERSION
        result["elapsed_seconds"] = round(time.perf_counter() - start, 2)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "top_suspects"}, ensure_ascii=False, indent=2))
    print("\nTop suspects (lowest plausibility edges):")
    for row in result["top_suspects"]:
        print(f"  score={row['score']:.3f} JD={row['support']:<3} | {row['s']} --[{row['p']}]--> {row['o']}")
    print(f"\nJSON summary saved to: {out_path}")


if __name__ == "__main__":
    main()
