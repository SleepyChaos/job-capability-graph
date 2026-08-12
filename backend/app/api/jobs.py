from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.job.models import (
    DataSource,
    DuplicateDocumentGroup,
    DuplicateDocumentMember,
    EvidenceSpan,
    JobPosting,
    JobPostingDataSource,
    JobRequirement,
    JobRequirementEvidence,
    JobScenario,
    Organization,
    SourceDocumentVersion,
)
from app.modules.taxonomy.models import TechnologyNode

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobSummaryResponse(BaseModel):
    total_jobs: int
    organization_count: int
    source_count: int
    unique_content_count: int
    duplicate_group_count: int
    duplicate_member_count: int
    source_timed_count: int
    migration_timed_count: int
    technology_covered_job_count: int
    requirement_count: int


class JobListItem(BaseModel):
    job_code: str
    source_job_id: str | None
    title: str
    company: str | None
    level: str | None
    region: str | None
    education: str | None
    experience: str | None
    source_collected_at: datetime | None
    time_quality: str
    evidence_weight: Decimal
    technology_count: int
    duplicate_group_code: str | None


class JobPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[JobListItem]


class JobTechnologyRequirement(BaseModel):
    requirement_no: int
    requirement_type: str
    technology_code: str
    technology_name: str
    raw_term: str | None
    mention_count: int
    confidence: Decimal
    evidence: list[str]


class JobDetailResponse(JobListItem):
    salary: str | None
    jd_text: str
    source_codes: list[str]
    technologies: list[JobTechnologyRequirement]
    scenarios: list[str] = []


def duplicate_group_subquery():
    return (
        select(
            DuplicateDocumentMember.source_document_version_id.label(
                "duplicate_document_version_id"
            ),
            DuplicateDocumentGroup.group_code.label("duplicate_group_code"),
        )
        .join(
            DuplicateDocumentGroup,
            DuplicateDocumentGroup.duplicate_group_id == DuplicateDocumentMember.duplicate_group_id,
        )
        .subquery()
    )


@router.get("/summary", response_model=JobSummaryResponse)
def job_summary(db: Annotated[Session, Depends(get_db)]) -> JobSummaryResponse:
    return JobSummaryResponse(
        total_jobs=db.scalar(select(func.count()).select_from(JobPosting)) or 0,
        organization_count=db.scalar(select(func.count()).select_from(Organization)) or 0,
        source_count=db.scalar(select(func.count()).select_from(DataSource)) or 0,
        unique_content_count=db.scalar(
            select(func.count(func.distinct(SourceDocumentVersion.content_hash)))
        )
        or 0,
        duplicate_group_count=db.scalar(select(func.count()).select_from(DuplicateDocumentGroup))
        or 0,
        duplicate_member_count=db.scalar(select(func.count()).select_from(DuplicateDocumentMember))
        or 0,
        source_timed_count=db.scalar(
            select(func.count())
            .select_from(JobPosting)
            .where(JobPosting.time_quality_code == "source_collected")
        )
        or 0,
        migration_timed_count=db.scalar(
            select(func.count())
            .select_from(JobPosting)
            .where(JobPosting.time_quality_code == "migration_only")
        )
        or 0,
        technology_covered_job_count=db.scalar(
            select(func.count(func.distinct(JobRequirement.job_posting_id)))
        )
        or 0,
        requirement_count=db.scalar(select(func.count()).select_from(JobRequirement)) or 0,
    )


@router.get("", response_model=JobPage)
def list_jobs(
    db: Annotated[Session, Depends(get_db)],
    search: str | None = None,
    source_code: str | None = None,
    level: Literal["junior", "middle", "senior"] | None = None,
    education: str | None = None,
    time_quality: Literal["source_collected", "migration_only"] | None = None,
    duplicate_only: bool = False,
    technology_code: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobPage:
    duplicate_group = duplicate_group_subquery()
    technology_count = (
        select(
            JobRequirement.job_posting_id.label("requirement_job_id"),
            func.count(func.distinct(JobRequirement.technology_node_id)).label("technology_count"),
        )
        .group_by(JobRequirement.job_posting_id)
        .subquery()
    )
    filters = []
    if search:
        pattern = f"%{search.strip().casefold()}%"
        filters.append(
            or_(
                JobPosting.job_title_normalized.like(pattern),
                Organization.normalized_name.like(pattern),
                JobPosting.source_job_id.like(f"%{search.strip()}%"),
            )
        )
    if level:
        filters.append(JobPosting.job_level_code == level)
    if education:
        filters.append(JobPosting.education_code == education)
    if time_quality:
        filters.append(JobPosting.time_quality_code == time_quality)
    if duplicate_only:
        filters.append(duplicate_group.c.duplicate_group_code.is_not(None))
    if source_code:
        filters.append(
            exists(
                select(1)
                .select_from(JobPostingDataSource)
                .join(DataSource, DataSource.data_source_id == JobPostingDataSource.data_source_id)
                .where(
                    JobPostingDataSource.job_posting_id == JobPosting.job_posting_id,
                    DataSource.source_code == source_code,
                )
            )
        )
    if technology_code:
        filters.append(
            exists(
                select(1)
                .select_from(JobRequirement)
                .join(
                    TechnologyNode,
                    TechnologyNode.technology_node_id == JobRequirement.technology_node_id,
                )
                .where(
                    JobRequirement.job_posting_id == JobPosting.job_posting_id,
                    TechnologyNode.technology_code == technology_code,
                )
            )
        )

    base = (
        select(
            JobPosting,
            Organization.canonical_name,
            func.coalesce(technology_count.c.technology_count, 0),
            duplicate_group.c.duplicate_group_code,
        )
        .outerjoin(Organization, Organization.organization_id == JobPosting.organization_id)
        .outerjoin(
            technology_count,
            technology_count.c.requirement_job_id == JobPosting.job_posting_id,
        )
        .outerjoin(
            duplicate_group,
            duplicate_group.c.duplicate_document_version_id
            == JobPosting.source_document_version_id,
        )
        .where(*filters)
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.execute(
        base.order_by(JobPosting.source_collected_at.desc(), JobPosting.job_posting_id)
        .offset(offset)
        .limit(limit)
    ).all()
    return JobPage(
        total=total,
        limit=limit,
        offset=offset,
        items=[
            job_item(job, company, technology_total, duplicate_code)
            for job, company, technology_total, duplicate_code in rows
        ],
    )


@router.get("/{job_code}", response_model=JobDetailResponse)
def job_detail(job_code: str, db: Annotated[Session, Depends(get_db)]) -> JobDetailResponse:
    duplicate_group = duplicate_group_subquery()
    row = db.execute(
        select(JobPosting, Organization.canonical_name, duplicate_group.c.duplicate_group_code)
        .outerjoin(Organization, Organization.organization_id == JobPosting.organization_id)
        .outerjoin(
            duplicate_group,
            duplicate_group.c.duplicate_document_version_id
            == JobPosting.source_document_version_id,
        )
        .where(JobPosting.job_code == job_code)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="JD不存在")
    job, company, duplicate_code = row
    source_codes = list(
        db.scalars(
            select(DataSource.source_code)
            .join(
                JobPostingDataSource,
                JobPostingDataSource.data_source_id == DataSource.data_source_id,
            )
            .where(JobPostingDataSource.job_posting_id == job.job_posting_id)
            .order_by(JobPostingDataSource.source_order)
        )
    )
    requirement_rows = db.execute(
        select(JobRequirement, TechnologyNode)
        .join(
            TechnologyNode,
            TechnologyNode.technology_node_id == JobRequirement.technology_node_id,
        )
        .where(JobRequirement.job_posting_id == job.job_posting_id)
        .order_by(JobRequirement.requirement_no)
    ).all()
    technologies = []
    for requirement, technology in requirement_rows:
        evidence = list(
            db.scalars(
                select(EvidenceSpan.evidence_text)
                .join(
                    JobRequirementEvidence,
                    JobRequirementEvidence.evidence_span_id == EvidenceSpan.evidence_span_id,
                )
                .where(JobRequirementEvidence.job_requirement_id == requirement.job_requirement_id)
                .order_by(EvidenceSpan.start_offset)
            )
        )
        technologies.append(
            JobTechnologyRequirement(
                requirement_no=requirement.requirement_no,
                requirement_type=requirement.requirement_type_code,
                technology_code=technology.technology_code,
                technology_name=technology.technology_name,
                raw_term=requirement.raw_term,
                mention_count=requirement.mention_count,
                confidence=requirement.confidence_score,
                evidence=evidence,
            )
        )
    technology_count = len(
        {
            requirement.technology_node_id
            for requirement, _technology in requirement_rows
            if requirement.technology_node_id is not None
        }
    )
    item = job_item(job, company, technology_count, duplicate_code)
    scenarios = list(
        db.scalars(
            select(JobScenario.scenario_text)
            .where(JobScenario.job_posting_id == job.job_posting_id)
            .order_by(JobScenario.scenario_no)
        )
    )
    return JobDetailResponse(
        **item.model_dump(),
        salary=job.salary_text,
        jd_text=job.jd_clean_text,
        source_codes=source_codes,
        technologies=technologies,
        scenarios=scenarios,
    )


def job_item(
    job: JobPosting,
    company: str | None,
    technology_count: int,
    duplicate_code: str | None,
) -> JobListItem:
    return JobListItem(
        job_code=job.job_code,
        source_job_id=job.source_job_id,
        title=job.job_title_raw,
        company=company or job.company_name_raw,
        level=job.job_level_code,
        region=job.region_text,
        education=job.education_code,
        experience=job.experience_text,
        source_collected_at=job.source_collected_at,
        time_quality=job.time_quality_code,
        evidence_weight=job.evidence_weight,
        technology_count=technology_count,
        duplicate_group_code=duplicate_code,
    )
