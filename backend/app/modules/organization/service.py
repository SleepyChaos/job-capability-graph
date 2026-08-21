"""组织/企业图谱投影与实体详情（RC-03 企业图谱视图 C/D + 侧栏全字段）。

视图：
  - enterprise_technology (C)：企业 ↔ 标准技术（来自 rel_org_technology，含 Layer B 外部佐证标记）
  - enterprise_job (D)：企业 ↔ 在聘岗位（基于企业名归一，与 biz_job_posting 真实 JD 数据关联）

实体详情：返回 OrganizationEntity 全部结构化字段 + 原始字段(raw_fields_json) + 技术/人才/交叉验证，
用于前端侧栏"已有字段全展示"。
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.ingestion.models import primary_key_type  # noqa: F401  (kept for parity)
from app.modules.job.models import JobPosting
from app.modules.organization.ingest import _norm
from app.modules.organization.models import (
    ORG_CATEGORY_ENTERPRISE,
    ORG_CATEGORY_RESEARCH,
    ORG_CATEGORY_UNIVERSITY,
    OrganizationCrossValidation,
    OrganizationEntity,
    OrganizationTechnology,
    OrganizationTalent,
    Talent,
)

ORG_CATEGORY_LABEL = {
    ORG_CATEGORY_ENTERPRISE: "企业",
    ORG_CATEGORY_UNIVERSITY: "高校",
    ORG_CATEGORY_RESEARCH: "科研院所",
    "other": "其他",
}

# 节点类型 -> 颜色（前端同步定义，后端仅作图例回传）
TYPE_COLORS = {
    "organization": "#2563eb",
    "technology": "#0d9488",
    "job": "#d97706",
}
CATEGORY_COLORS = {
    ORG_CATEGORY_ENTERPRISE: "#2563eb",
    ORG_CATEGORY_UNIVERSITY: "#7c3aed",
    ORG_CATEGORY_RESEARCH: "#0891b2",
    "other": "#64748b",
}


def _domain_code(code: str | None) -> str:
    if not code:
        return "T7"
    return code.split(".")[0][:2] or "T7"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _orgs_with_tech(db: Session, category: str | None, limit: int):
    subq = (
        db.query(
            OrganizationTechnology.org_id,
            func.count().label("tc"),
        )
        .group_by(OrganizationTechnology.org_id)
        .subquery()
    )
    q = db.query(OrganizationEntity).join(subq, OrganizationEntity.org_id == subq.c.org_id)
    if category:
        q = q.filter(OrganizationEntity.org_category == category)
    return q.order_by(subq.c.tc.desc()).limit(limit).all()


def get_enterprise_tech_graph(
    db: Session,
    *,
    category: str | None = None,
    limit: int = 400,
) -> dict:
    """视图 C：企业 ↔ 标准技术。"""
    orgs = _orgs_with_tech(db, category, limit)
    org_ids = [o.org_id for o in orgs]

    tech_rows = (
        db.query(OrganizationTechnology)
        .filter(OrganizationTechnology.org_id.in_(org_ids))
        .all()
    )
    tech_by_org: dict[int, list[OrganizationTechnology]] = {}
    tech_degree: dict[str, int] = {}
    for t in tech_rows:
        tech_by_org.setdefault(t.org_id, []).append(t)
        tech_degree[t.technology_code] = tech_degree.get(t.technology_code, 0) + 1

    nodes = []
    edges = []
    seen_tech = set()
    for o in orgs:
        first_tech = (tech_by_org.get(o.org_id, []) or [None])[0]
        org_domain = o.industry_chain or (first_tech.technology_code if first_tech else None)
        nodes.append({
            "id": f"org:{o.org_id}",
            "type": "organization",
            "category": o.org_category,
            "label": o.org_name,
            "domain_code": _domain_code(org_domain),
            "weight": len(tech_by_org.get(o.org_id, [])),
            "metrics": {
                "tech_count": len(tech_by_org.get(o.org_id, [])),
                "patent_family_count": o.patent_family_count,
                "standard_count": o.standard_count,
                "job_posting_count": o.job_posting_count,
                "external_alignment_rate": round(o.external_alignment_rate, 3),
            },
        })
        for t in tech_by_org.get(o.org_id, []):
            tid = f"tech:{t.technology_code}"
            if tid not in seen_tech:
                seen_tech.add(tid)
                nodes.append({
                    "id": tid,
                    "type": "technology",
                    "label": t.technology_name,
                    "domain_code": _domain_code(t.technology_code),
                    "weight": tech_degree.get(t.technology_code, 1),
                    "metrics": {"org_degree": tech_degree.get(t.technology_code, 1)},
                })
            edges.append({
                "id": f"ot:{o.org_id}:{t.technology_code}",
                "source": f"org:{o.org_id}",
                "target": tid,
                "relation_type": "org_technology",
                "weight": t.mention_count or 1,
                "external_aligned": bool(t.external_aligned),
                "external_skill_label": t.external_skill_label,
                "level_code": t.level_code,
            })

    return _wrap(
        "enterprise_technology",
        nodes,
        edges,
        f"企业↔技术（{ORG_CATEGORY_LABEL.get(category, '全部机构') if category else '全部机构'}）",
    )


def get_enterprise_job_graph(
    db: Session,
    *,
    category: str | None = None,
    limit: int = 300,
) -> dict:
    """视图 D：企业 ↔ 在聘岗位。基于企业名归一关联 biz_job_posting 真实 JD 数据。"""
    orgs = _orgs_with_tech(db, category, limit)
    if category:
        orgs = [o for o in orgs if o.org_category == category]

    # 真实 JD 数据：按公司名聚合在聘岗位数（用于佐证/补充，非主边来源）
    job_rows = (
        db.query(JobPosting.company_name_raw, func.count().label("cnt"))
        .filter(JobPosting.company_name_raw.isnot(None))
        .group_by(JobPosting.company_name_raw)
        .all()
    )
    company_norm = {}
    for raw, cnt in job_rows:
        nk = _norm(raw)
        if not nk:
            continue
        prev = company_norm.get(nk)
        if prev is None or cnt > prev[1]:
            company_norm[nk] = (str(raw), int(cnt))

    nodes = []
    edges = []
    seen_job = set()
    for o in orgs:
        nk = _norm(o.org_name)
        # 主边来源：来源表自带的在聘岗位数量（企业岗位整合 Sheet 的真实字段）
        jpc = int(o.job_posting_count or 0)
        # 佐证：与真实 JD 库（biz_job_posting）按归一名匹配
        real = company_norm.get(nk)
        real_cnt = real[1] if real else 0
        nodes.append({
            "id": f"org:{o.org_id}",
            "type": "organization",
            "category": o.org_category,
            "label": o.org_name,
            "domain_code": _domain_code(o.industry_chain),
            "weight": max(jpc, real_cnt),
            "metrics": {
                "job_posting_count": jpc,
                "real_jd_postings": real_cnt,
                "patent_family_count": o.patent_family_count,
                "standard_count": o.standard_count,
            },
        })
        # 仅当来源表自带在聘岗位数 > 0 时绘制企业↔岗位边
        if jpc > 0:
            jid = f"job:{o.org_id}"
            if jid not in seen_job:
                seen_job.add(jid)
                label = f"{o.org_name} · 在聘岗位" if not real else f"{real[0]} · 在聘岗位(含真实JD)"
                nodes.append({
                    "id": jid,
                    "type": "job",
                    "label": label,
                    "domain_code": _domain_code(o.industry_chain),
                    "weight": jpc,
                    "metrics": {"posting_count": jpc, "real_jd_postings": real_cnt},
                })
            edges.append({
                "id": f"oj:{o.org_id}",
                "source": f"org:{o.org_id}",
                "target": jid,
                "relation_type": "org_job",
                "weight": jpc,
                "posting_count": jpc,
                "real_jd_postings": real_cnt,
            })

    return _wrap(
        "enterprise_job",
        nodes,
        edges,
        f"企业↔在聘岗位（{ORG_CATEGORY_LABEL.get(category, '全部机构') if category else '全部机构'}）",
    )


def get_entity_detail(db: Session, org_id: int) -> dict:
    """实体详情：全字段 + 关联技术/人才/交叉验证。侧栏'已有字段全展示'的数据源。"""
    org = db.get(OrganizationEntity, org_id)
    if org is None:
        raise EntityNotFound(org_id)

    cols = {c.name: getattr(org, c.name) for c in OrganizationEntity.__table__.columns}
    # raw_fields_json 已是 dict（来源表全部原始字段）
    raw = cols.get("raw_fields_json") or {}

    techs = (
        db.query(OrganizationTechnology)
        .filter(OrganizationTechnology.org_id == org_id)
        .order_by(OrganizationTechnology.mention_count.desc())
        .all()
    )
    tech_list = [
        {
            "technology_code": t.technology_code,
            "technology_name": t.technology_name,
            "level_code": t.level_code,
            "mention_count": t.mention_count,
            "annotation_source": t.annotation_source,
            "external_aligned": bool(t.external_aligned),
            "external_skill_label": t.external_skill_label,
        }
        for t in techs
    ]

    talent_rows = (
        db.query(Talent, OrganizationTalent.relation_type, OrganizationTalent.source)
        .join(OrganizationTalent, OrganizationTalent.talent_id == Talent.talent_id)
        .filter(OrganizationTalent.org_id == org_id)
        .all()
    )
    talent_list = [
        {
            "talent_code": t.talent_code,
            "display_name": t.display_name,
            "talent_type": t.talent_type,
            "title": t.title,
            "primary_org_name": t.primary_org_name,
            "relation_type": rel,
            "source": src,
        }
        for t, rel, src in talent_rows
    ]

    cv = db.query(OrganizationCrossValidation).filter(
        OrganizationCrossValidation.org_id == org_id
    ).first()
    cv_dict = None
    if cv is not None:
        cv_dict = {c.name: getattr(cv, c.name) for c in OrganizationCrossValidation.__table__.columns}

    return {
        "org_id": org_id,
        "category_label": ORG_CATEGORY_LABEL.get(org.org_category, org.org_category),
        "fields": cols,                 # 全部结构化字段
        "raw_fields": raw,              # 来源表全部原始字段（侧栏展开）
        "technologies": tech_list,
        "talents": talent_list,
        "cross_validation": cv_dict,
        "generated_at": _now_iso(),
    }


class EntityNotFound(Exception):
    def __init__(self, org_id: int):
        super().__init__(f"组织实体不存在：{org_id}")
        self.org_id = org_id


def _wrap(view: str, nodes: list, edges: list, title: str) -> dict:
    legend = [
        {"type": "organization", "label": "机构", "color": TYPE_COLORS["organization"]},
        {"type": "technology", "label": "标准技术", "color": TYPE_COLORS["technology"]},
        {"type": "job", "label": "在聘岗位", "color": TYPE_COLORS["job"]},
    ]
    return {
        "view": view,
        "title": title,
        "metadata": {
            "generated_at": _now_iso(),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "evidence_policy": "real_source_xlsx_plus_splink_dedupe",
        },
        "legend": legend,
        "nodes": nodes,
        "edges": edges,
    }
