from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.job.models import (
    EvidenceSpan,
    JobClusterFeatureSnapshot,
    JobParseResult,
    JobParseRun,
    JobPosting,
    JobRequirement,
    JobResponsibility,
    Organization,
    TechnologyAmbiguityRule,
    TechnologyMatchAssessment,
)
from app.modules.taxonomy.models import TechnologyNode

router = APIRouter(prefix="/job-parsing", tags=["job-parsing"])


class ParseRunItem(BaseModel):
    run_code: str
    parser_version: str
    target_date: date
    status: str
    input_job_count: int
    parsed_job_count: int
    review_job_count: int
    responsibility_count: int
    assessment_count: int
    feature_count: int
    started_at: datetime
    completed_at: datetime | None


class ParsingSummary(BaseModel):
    run: ParseRunItem
    average_quality_score: Decimal
    ambiguity_review_count: int
    eligible_feature_count: int
    excluded_feature_count: int


class ParsedJobItem(BaseModel):
    job_code: str
    title: str
    company: str | None
    parse_status: str
    parse_quality_score: Decimal
    responsibility_count: int
    ambiguity_review_count: int
    review_required: bool
    eligible_for_clustering: bool
    time_quality: str
    sample_weight: Decimal


class ParsedJobPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ParsedJobItem]


class ResponsibilityItem(BaseModel):
    number: int
    raw_text: str
    normalized_task: str | None
    action_verb: str | None
    task_object: str | None
    expected_output: str | None
    confidence: Decimal


class TechnologyAssessmentItem(BaseModel):
    technology_code: str
    technology_name: str
    matched_text: str
    context_text: str | None
    context_type: str
    status: str
    adjusted_support_score: Decimal
    feature_weight: Decimal
    reason: str


class FeatureItem(BaseModel):
    version: str
    title_tokens: list[str]
    responsibility_tokens: list[str]
    technology_weights: dict[str, float]
    domain_weights: dict[str, float]
    level: str | None
    sample_weight: Decimal
    time_quality: str
    eligible: bool
    exclusion_reasons: list[str]


class ParsedJobDetail(ParsedJobItem):
    run_code: str
    reasons: list[str]
    responsibilities: list[ResponsibilityItem]
    technology_assessments: list[TechnologyAssessmentItem]
    cluster_feature: FeatureItem


class AmbiguityRuleItem(BaseModel):
    rule_code: str
    alias: str
    technology_code: str
    technology_name: str
    positive_markers: list[str]
    missing_context_decision: str
    review_weight: Decimal
    version: str
    active: bool


def latest_run(db: Session) -> JobParseRun:
    run = db.scalar(
        select(JobParseRun)
        .where(JobParseRun.run_status_code == "completed")
        .order_by(JobParseRun.completed_at.desc(), JobParseRun.job_parse_run_id.desc())
        .limit(1)
    )
    if run is None:
        raise HTTPException(status_code=404, detail="尚无已完成的JD解析运行")
    return run


def run_item(run: JobParseRun) -> ParseRunItem:
    return ParseRunItem(
        run_code=run.run_code,
        parser_version=run.parser_version,
        target_date=run.target_date,
        status=run.run_status_code,
        input_job_count=run.input_job_count,
        parsed_job_count=run.parsed_job_count,
        review_job_count=run.review_job_count,
        responsibility_count=run.responsibility_count,
        assessment_count=run.assessment_count,
        feature_count=run.feature_count,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


@router.get("/runs", response_model=list[ParseRunItem])
def parse_runs(db: Annotated[Session, Depends(get_db)]) -> list[ParseRunItem]:
    return [
        run_item(run)
        for run in db.scalars(
            select(JobParseRun).order_by(
                JobParseRun.started_at.desc(), JobParseRun.job_parse_run_id.desc()
            )
        )
    ]


@router.get("/summary", response_model=ParsingSummary)
def parsing_summary(db: Annotated[Session, Depends(get_db)]) -> ParsingSummary:
    run = latest_run(db)
    average_quality = db.scalar(
        select(func.avg(JobParseResult.parse_quality_score)).where(
            JobParseResult.job_parse_run_id == run.job_parse_run_id
        )
    ) or Decimal("0")
    ambiguity_reviews = (
        db.scalar(
            select(func.count())
            .select_from(TechnologyMatchAssessment)
            .where(
                TechnologyMatchAssessment.job_parse_run_id == run.job_parse_run_id,
                TechnologyMatchAssessment.assessment_status_code == "needs_review",
            )
        )
        or 0
    )
    eligible = (
        db.scalar(
            select(func.count())
            .select_from(JobClusterFeatureSnapshot)
            .where(
                JobClusterFeatureSnapshot.job_parse_run_id == run.job_parse_run_id,
                JobClusterFeatureSnapshot.eligible_for_clustering.is_(True),
            )
        )
        or 0
    )
    return ParsingSummary(
        run=run_item(run),
        average_quality_score=Decimal(str(average_quality)).quantize(Decimal("0.01")),
        ambiguity_review_count=ambiguity_reviews,
        eligible_feature_count=eligible,
        excluded_feature_count=run.feature_count - eligible,
    )


@router.get("/jobs", response_model=ParsedJobPage)
def parsed_jobs(
    db: Annotated[Session, Depends(get_db)],
    review_required: bool | None = None,
    eligible: bool | None = None,
    min_quality: Annotated[Decimal | None, Query(ge=0, le=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ParsedJobPage:
    run = latest_run(db)
    statement = (
        select(
            JobPosting,
            Organization.canonical_name,
            JobParseResult,
            JobClusterFeatureSnapshot,
        )
        .join(JobParseResult, JobParseResult.job_posting_id == JobPosting.job_posting_id)
        .join(
            JobClusterFeatureSnapshot,
            JobClusterFeatureSnapshot.job_posting_id == JobPosting.job_posting_id,
        )
        .outerjoin(Organization, Organization.organization_id == JobPosting.organization_id)
        .where(
            JobParseResult.job_parse_run_id == run.job_parse_run_id,
            JobClusterFeatureSnapshot.job_parse_run_id == run.job_parse_run_id,
        )
    )
    if review_required is not None:
        statement = statement.where(JobParseResult.review_required.is_(review_required))
    if eligible is not None:
        statement = statement.where(JobClusterFeatureSnapshot.eligible_for_clustering.is_(eligible))
    if min_quality is not None:
        statement = statement.where(JobParseResult.parse_quality_score >= min_quality)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.execute(
        statement.order_by(
            JobParseResult.review_required.desc(),
            JobParseResult.parse_quality_score,
            JobPosting.job_posting_id,
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return ParsedJobPage(
        total=total,
        limit=limit,
        offset=offset,
        items=[parsed_item(*row) for row in rows],
    )


@router.get("/jobs/{job_code}", response_model=ParsedJobDetail)
def parsed_job_detail(job_code: str, db: Annotated[Session, Depends(get_db)]) -> ParsedJobDetail:
    run = latest_run(db)
    row = db.execute(
        select(
            JobPosting,
            Organization.canonical_name,
            JobParseResult,
            JobClusterFeatureSnapshot,
        )
        .join(JobParseResult, JobParseResult.job_posting_id == JobPosting.job_posting_id)
        .join(
            JobClusterFeatureSnapshot,
            JobClusterFeatureSnapshot.job_posting_id == JobPosting.job_posting_id,
        )
        .outerjoin(Organization, Organization.organization_id == JobPosting.organization_id)
        .where(
            JobPosting.job_code == job_code,
            JobParseResult.job_parse_run_id == run.job_parse_run_id,
            JobClusterFeatureSnapshot.job_parse_run_id == run.job_parse_run_id,
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="解析结果不存在")
    job, company, parse_result, feature = row
    responsibilities = [
        ResponsibilityItem(
            number=item.responsibility_no,
            raw_text=item.raw_text,
            normalized_task=item.normalized_task_text,
            action_verb=item.action_verb,
            task_object=item.task_object,
            expected_output=item.expected_output,
            confidence=item.confidence_score,
        )
        for item in db.scalars(
            select(JobResponsibility)
            .where(
                JobResponsibility.job_parse_run_id == run.job_parse_run_id,
                JobResponsibility.job_posting_id == job.job_posting_id,
            )
            .order_by(JobResponsibility.responsibility_no)
        )
    ]
    assessments: list[TechnologyAssessmentItem] = []
    for assessment, _requirement, technology, evidence in db.execute(
        select(
            TechnologyMatchAssessment,
            JobRequirement,
            TechnologyNode,
            EvidenceSpan,
        )
        .join(
            JobRequirement,
            JobRequirement.job_requirement_id == TechnologyMatchAssessment.job_requirement_id,
        )
        .join(
            TechnologyNode,
            TechnologyNode.technology_node_id == JobRequirement.technology_node_id,
        )
        .join(
            EvidenceSpan,
            EvidenceSpan.evidence_span_id == TechnologyMatchAssessment.evidence_span_id,
        )
        .where(
            TechnologyMatchAssessment.job_parse_run_id == run.job_parse_run_id,
            JobRequirement.job_posting_id == job.job_posting_id,
        )
        .order_by(TechnologyMatchAssessment.technology_match_assessment_id)
    ).all():
        context = (
            db.get(EvidenceSpan, assessment.context_evidence_span_id)
            if assessment.context_evidence_span_id
            else None
        )
        assessments.append(
            TechnologyAssessmentItem(
                technology_code=technology.technology_code,
                technology_name=technology.technology_name,
                matched_text=evidence.evidence_text,
                context_text=context.evidence_text if context else None,
                context_type=assessment.context_type_code,
                status=assessment.assessment_status_code,
                adjusted_support_score=assessment.adjusted_support_score,
                feature_weight=assessment.feature_weight,
                reason=assessment.reason_code,
            )
        )
    item = parsed_item(job, company, parse_result, feature)
    return ParsedJobDetail(
        **item.model_dump(),
        run_code=run.run_code,
        reasons=(parse_result.reason_json or {}).get("reasons", []),
        responsibilities=responsibilities,
        technology_assessments=assessments,
        cluster_feature=FeatureItem(
            version=feature.feature_version,
            title_tokens=feature.title_tokens_json,
            responsibility_tokens=feature.responsibility_tokens_json,
            technology_weights=feature.technology_weights_json,
            domain_weights=feature.domain_weights_json,
            level=feature.level_code,
            sample_weight=feature.sample_weight,
            time_quality=feature.time_quality_code,
            eligible=feature.eligible_for_clustering,
            exclusion_reasons=feature.exclusion_reason_json or [],
        ),
    )


@router.get("/ambiguity-rules", response_model=list[AmbiguityRuleItem])
def ambiguity_rules(db: Annotated[Session, Depends(get_db)]) -> list[AmbiguityRuleItem]:
    return [
        AmbiguityRuleItem(
            rule_code=rule.rule_code,
            alias=rule.normalized_alias,
            technology_code=technology.technology_code,
            technology_name=technology.technology_name,
            positive_markers=rule.positive_markers_json,
            missing_context_decision=rule.missing_context_decision_code,
            review_weight=rule.review_weight,
            version=rule.rule_version,
            active=rule.is_active,
        )
        for rule, technology in db.execute(
            select(TechnologyAmbiguityRule, TechnologyNode)
            .join(
                TechnologyNode,
                TechnologyNode.technology_node_id == TechnologyAmbiguityRule.technology_node_id,
            )
            .order_by(TechnologyAmbiguityRule.rule_code)
        ).all()
    ]


def parsed_item(
    job: JobPosting,
    company: str | None,
    parse_result: JobParseResult,
    feature: JobClusterFeatureSnapshot,
) -> ParsedJobItem:
    return ParsedJobItem(
        job_code=job.job_code,
        title=job.job_title_raw,
        company=company or job.company_name_raw,
        parse_status=parse_result.parse_status_code,
        parse_quality_score=parse_result.parse_quality_score,
        responsibility_count=parse_result.responsibility_count,
        ambiguity_review_count=parse_result.ambiguity_review_count,
        review_required=parse_result.review_required,
        eligible_for_clustering=feature.eligible_for_clustering,
        time_quality=feature.time_quality_code,
        sample_weight=feature.sample_weight,
    )
