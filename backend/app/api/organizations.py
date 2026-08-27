"""Organization API — cross-source org entities (Layer A Splink output)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.clustering.models import JobClusterMember, JobClusterVersion
from app.modules.job.models import (
    JobPosting,
    JobRequirement,
    Organization,
    OrganizationAlias,
)
from app.modules.organization.models import (
    OrganizationCrossValidation,
    OrganizationEntity,
    OrganizationTalent,
    OrganizationTechnology,
    Talent,
)
from app.modules.taxonomy.models import TechnologyNode

router = APIRouter(prefix="/organizations", tags=["organizations"])


class OrganizationListItem(BaseModel):
    code: str
    name: str
    type: str
    province: str | None
    city: str | None
    status: str
    aliases_preview: list[str]
    job_count: int
    referenced_technology_count: int
    cluster_count: int
    min_match_score: float | None
    needs_review: bool


class OrganizationPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[OrganizationListItem]


class OrganizationDetailItem(BaseModel):
    code: str
    name: str
    normalized_name: str
    type: str
    province: str | None
    city: str | None
    website: str | None
    industry_text: str | None
    status: str
    aliases: list[str]
    job_count: int
    cluster_count: int
    referenced_technology_count: int
    top_technologies: list[dict]  # [{code,name,count}]
    top_clusters: list[dict]  # [{code,label,job_count}]
    splink_meta: dict | None


class CrossValidationPage(BaseModel):
    summary: dict
    rows: list[dict]
    limit: int
    offset: int


def _aggregate_stats(db: Session, org_ids: list[int]) -> tuple[dict, dict, dict]:
    """Return org_id->job_count, org_id->tech_counts, org_id->cluster_counts"""
    job_count: dict[int, int] = {}
    rows = db.execute(
        select(JobPosting.organization_id, func.count())
        .where(JobPosting.organization_id.in_(org_ids))
        .group_by(JobPosting.organization_id)
    ).all()
    for oid, cnt in rows:
        if oid:
            job_count[oid] = int(cnt)

    tech_counts: dict[int, dict[str, int]] = {}
    rows = db.execute(
        select(
            JobPosting.organization_id,
            JobRequirement.technology_node_id,
            func.count(JobRequirement.job_requirement_id),
        )
        .join(JobPosting, JobPosting.job_posting_id == JobRequirement.job_posting_id)
        .where(
            JobPosting.organization_id.in_(org_ids),
            JobRequirement.technology_node_id.is_not(None),
        )
        .group_by(JobPosting.organization_id, JobRequirement.technology_node_id)
    ).all()
    node_id_to_code: dict[int, tuple[str, str]] = {}
    node_ids = sorted({nid for _, nid, _ in rows})
    if node_ids:
        node_rows = db.execute(
            select(
                TechnologyNode.technology_node_id,
                TechnologyNode.technology_code,
                TechnologyNode.technology_name,
            ).where(TechnologyNode.technology_node_id.in_(node_ids))
        ).all()
        for nid, code, name in node_rows:
            node_id_to_code[nid] = (code, name)
    for oid, nid, cnt in rows:
        if not oid or nid not in node_id_to_code:
            continue
        d = tech_counts.setdefault(oid, {})
        d[node_id_to_code[nid][0] + "|" + node_id_to_code[nid][1]] = int(
            d.get(node_id_to_code[nid][0] + "|" + node_id_to_code[nid][1], 0) + int(cnt)
        )

    cluster_counts: dict[int, dict[str, tuple[str, int]]] = {}
    rows = db.execute(
        select(
            JobPosting.organization_id,
            JobClusterVersion.stable_cluster_code,
            JobClusterVersion.cluster_label,
            func.count(JobClusterMember.job_posting_id),
        )
        .join(JobPosting, JobPosting.job_posting_id == JobClusterMember.job_posting_id)
        .join(
            JobClusterVersion,
            JobClusterVersion.job_cluster_version_id == JobClusterMember.job_cluster_version_id,
        )
        .where(JobPosting.organization_id.in_(org_ids))
        .group_by(JobPosting.organization_id, JobClusterVersion.job_cluster_version_id)
    ).all()
    for oid, code, label, cnt in rows:
        if not oid:
            continue
        d = cluster_counts.setdefault(oid, {})
        d[code] = (label, int(d.get(code, (label, 0))[1] + int(cnt)))

    return job_count, tech_counts, cluster_counts


@router.get("", response_model=OrganizationPage)
def list_organizations(
    db: Annotated[Session, Depends(get_db)],
    search: str | None = None,
    org_type: str | None = None,
    only_needs_review: bool = False,
    with_jobs_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OrganizationPage:
    filters = []
    if search:
        pattern = f"%{search.strip().casefold()}%"
        filters.append(
            or_(
                Organization.normalized_name.like(pattern),
                Organization.canonical_name.like(f"%{search.strip()}%"),
                Organization.organization_code.like(f"%{search.strip()}%"),
                exists(
                    select(1).where(
                        OrganizationAlias.organization_id == Organization.organization_id,
                        OrganizationAlias.normalized_alias.like(pattern),
                    )
                ),
            )
        )
    if org_type:
        filters.append(Organization.organization_type_code == org_type)
    if only_needs_review:
        filters.append(Organization.organization_status_code == "needs_review")

    base = select(Organization).where(and_(True, *filters))
    if with_jobs_only:
        base = base.where(
            exists(select(1).where(JobPosting.organization_id == Organization.organization_id))
        )

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    org_rows = list(
        db.scalars(
            base.order_by(
                Organization.organization_status_code != "active",
                Organization.organization_type_code,
                Organization.canonical_name,
            )
            .offset(offset)
            .limit(limit)
        )
    )
    org_ids = [o.organization_id for o in org_rows]
    job_count_map, tech_map, _cluster_map = (
        _aggregate_stats(db, org_ids) if org_ids else ({}, {}, {})
    )

    alias_map: dict[int, list[str]] = {}
    if org_ids:
        alias_rows = db.execute(
            select(OrganizationAlias.organization_id, OrganizationAlias.alias_text)
            .where(OrganizationAlias.organization_id.in_(org_ids))
            .order_by(OrganizationAlias.alias_type_code, OrganizationAlias.organization_alias_id)
        ).all()
        for oid, txt in alias_rows:
            alias_map.setdefault(oid, []).append(txt)

    items: list[OrganizationListItem] = []
    for o in org_rows:
        meta = o.source_metadata_json or {}
        splink_summary = meta.get("splink_summary", {}) if isinstance(meta, dict) else {}
        aliases = alias_map.get(o.organization_id, [])[:6]
        jobs = job_count_map.get(o.organization_id, 0)
        tech_cnt = len(tech_map.get(o.organization_id, {}))
        items.append(
            OrganizationListItem(
                code=o.organization_code,
                name=o.canonical_name,
                type=o.organization_type_code,
                province=o.province_name,
                city=o.city_name,
                status=o.organization_status_code,
                aliases_preview=aliases,
                job_count=jobs,
                referenced_technology_count=tech_cnt,
                cluster_count=0,  # placeholder, heavy count aggregated in detail
                min_match_score=splink_summary.get("min_match_score"),
                needs_review=splink_summary.get(
                    "needs_review", o.organization_status_code == "needs_review"
                ),
            )
        )
    return OrganizationPage(total=total, limit=limit, offset=offset, items=items)


@router.get("/cross-validation/report", response_model=CrossValidationPage)
def cross_validation_report(
    db: Annotated[Session, Depends(get_db)],
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CrossValidationPage:
    """Return traceable university/institute/company/talent/skill validation results."""
    try:
        filters = []
        if status:
            filters.append(OrganizationEntity.cross_validation_status == status)
        total_entities = db.scalar(select(func.count()).select_from(OrganizationEntity)) or 0
        category_rows = db.execute(
            select(OrganizationEntity.org_category, func.count()).group_by(
                OrganizationEntity.org_category
            )
        ).all()
        status_rows = db.execute(
            select(OrganizationEntity.cross_validation_status, func.count()).group_by(
                OrganizationEntity.cross_validation_status
            )
        ).all()
        talent_count = db.scalar(select(func.count()).select_from(Talent)) or 0
        org_talent_count = db.scalar(select(func.count()).select_from(OrganizationTalent)) or 0
        org_tech_count = db.scalar(select(func.count()).select_from(OrganizationTechnology)) or 0
        query = (
            select(OrganizationEntity, OrganizationCrossValidation)
            .outerjoin(
                OrganizationCrossValidation,
                OrganizationCrossValidation.org_id == OrganizationEntity.org_id,
            )
            .where(*filters)
            .order_by(
                OrganizationEntity.cross_validation_status,
                OrganizationEntity.org_category,
                OrganizationEntity.org_name,
            )
        )
        matched_total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        result_rows = db.execute(query.offset(offset).limit(limit)).all()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="交叉验证数据尚未初始化，请先执行 organization.ingest 导入。",
        ) from exc

    rows = []
    for org, cv in result_rows:
        rows.append(
            {
                "org_code": org.org_code,
                "org_name": org.org_name,
                "org_category": org.org_category,
                "province": org.hq_province,
                "city": org.hq_city,
                "source_count": len(org.dedup_source_keys or []),
                "splink_match_score": float(org.splink_match_score or 0),
                "external_alignment_rate": float(org.external_alignment_rate or 0),
                "status": org.cross_validation_status,
                "consistency_score": int(cv.consistency_score if cv else 0),
                "business_chain": cv.business_chain if cv else None,
                "patent_domain_codes": cv.patent_domain_codes if cv else None,
                "jd_chain": cv.jd_chain if cv else None,
                "matched_dimensions": int(cv.matched_dimensions if cv else 0),
                "missing_dimensions": list(cv.missing_dimensions_json or [])
                if cv
                else ["validation_record_missing"],
                "calculated_at": cv.calculated_at.isoformat() if cv and cv.calculated_at else None,
            }
        )
    return CrossValidationPage(
        summary={
            "entity_count": int(total_entities),
            "matched_entity_count": int(matched_total),
            "category_counts": {str(k or "unknown"): int(v) for k, v in category_rows},
            "status_counts": {str(k or "unverified"): int(v) for k, v in status_rows},
            "talent_count": int(talent_count),
            "organization_talent_edges": int(org_talent_count),
            "organization_technology_edges": int(org_tech_count),
        },
        rows=rows,
        limit=limit,
        offset=offset,
    )


@router.get("/{code}", response_model=OrganizationDetailItem)
def organization_detail(
    code: str, db: Annotated[Session, Depends(get_db)]
) -> OrganizationDetailItem:
    org = db.scalar(select(Organization).where(Organization.organization_code == code))
    if org is None:
        raise HTTPException(status_code=404, detail="机构不存在")
    aliases = list(
        db.scalars(
            select(OrganizationAlias.alias_text).where(
                OrganizationAlias.organization_id == org.organization_id
            )
        )
    )
    job_count_map, tech_counts, cluster_counts = _aggregate_stats(db, [org.organization_id])
    tc = tech_counts.get(org.organization_id, {})
    sorted_techs = sorted(tc.items(), key=lambda kv: kv[1], reverse=True)[:12]
    top_techs = []
    for key, cnt in sorted_techs:
        code_, name = key.split("|", 1)
        top_techs.append({"code": code_, "name": name, "count": cnt})

    cc = cluster_counts.get(org.organization_id, {})
    sorted_clusters = sorted(cc.items(), key=lambda kv: kv[1][1], reverse=True)[:12]
    top_clusters = [
        {"code": ccode, "label": label, "job_count": cnt} for ccode, (label, cnt) in sorted_clusters
    ]

    meta = org.source_metadata_json if isinstance(org.source_metadata_json, dict) else None

    return OrganizationDetailItem(
        code=org.organization_code,
        name=org.canonical_name,
        normalized_name=org.normalized_name,
        type=org.organization_type_code,
        province=org.province_name,
        city=org.city_name,
        website=org.website_url,
        industry_text=org.industry_text,
        status=org.organization_status_code,
        aliases=aliases,
        job_count=job_count_map.get(org.organization_id, 0),
        cluster_count=len(cc),
        referenced_technology_count=len(tc),
        top_technologies=top_techs,
        top_clusters=top_clusters,
        splink_meta=meta,
    )
