from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.job.models import JobPosting, Organization, OrganizationAlias

router = APIRouter(prefix="/organizations", tags=["organizations"])


class OrganizationSummary(BaseModel):
    total: int
    enterprise_count: int
    university_count: int
    research_institute_count: int
    government_public_count: int
    job_linked_count: int


class OrganizationListItem(BaseModel):
    organization_code: str
    institution_ids: list[str]
    name: str
    organization_type: str
    country: str | None
    province: str | None
    city: str | None
    website_url: str | None
    recruitment_url: str | None
    industry: str | None
    source: str | None
    job_count: int


class OrganizationPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[OrganizationListItem]


@router.get("/summary", response_model=OrganizationSummary)
def organization_summary(db: Annotated[Session, Depends(get_db)]):
    counts = dict(
        db.execute(
            select(Organization.organization_type_code, func.count())
            .group_by(Organization.organization_type_code)
        ).all()
    )
    return OrganizationSummary(
        total=sum(counts.values()),
        enterprise_count=counts.get("enterprise", 0),
        university_count=counts.get("university", 0),
        research_institute_count=counts.get("research_institute", 0),
        government_public_count=counts.get("government_public", 0),
        job_linked_count=db.scalar(
            select(func.count(func.distinct(JobPosting.organization_id))).where(
                JobPosting.organization_id.is_not(None)
            )
        )
        or 0,
    )


@router.get("", response_model=OrganizationPage)
def list_organizations(
    db: Annotated[Session, Depends(get_db)],
    search: str | None = None,
    organization_type: Literal[
        "enterprise", "university", "research_institute", "government_public", "other"
    ]
    | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    filters = []
    if search:
        pattern = f"%{search.strip().casefold()}%"
        alias_exists = (
            select(OrganizationAlias.organization_alias_id)
            .where(
                OrganizationAlias.organization_id == Organization.organization_id,
                OrganizationAlias.normalized_alias.like(pattern),
            )
            .exists()
        )
        filters.append(
            or_(
                Organization.normalized_name.like(pattern),
                Organization.canonical_name.like(f"%{search.strip()}%"),
                alias_exists,
            )
        )
    if organization_type:
        filters.append(Organization.organization_type_code == organization_type)
    total = db.scalar(select(func.count()).select_from(Organization).where(*filters)) or 0
    job_counts = (
        select(JobPosting.organization_id, func.count().label("job_count"))
        .where(JobPosting.organization_id.is_not(None))
        .group_by(JobPosting.organization_id)
        .subquery()
    )
    rows = db.execute(
        select(Organization, func.coalesce(job_counts.c.job_count, 0))
        .outerjoin(job_counts, job_counts.c.organization_id == Organization.organization_id)
        .where(*filters)
        .order_by(Organization.canonical_name, Organization.organization_id)
        .limit(limit)
        .offset(offset)
    ).all()
    items = []
    for organization, job_count in rows:
        metadata = organization.source_metadata_json or {}
        items.append(
            OrganizationListItem(
                organization_code=organization.organization_code,
                institution_ids=list(metadata.get("institution_ids") or []),
                name=organization.canonical_name,
                organization_type=organization.organization_type_code,
                country=organization.country_code,
                province=organization.province_name,
                city=organization.city_name,
                website_url=organization.website_url,
                recruitment_url=metadata.get("recruitment_url"),
                industry=organization.industry_text,
                source=metadata.get("source"),
                job_count=int(job_count),
            )
        )
    return OrganizationPage(total=total, limit=limit, offset=offset, items=items)
