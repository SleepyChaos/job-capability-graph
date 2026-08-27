import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.data_center.models import (
    CollectionRequest,
    CollectionRun,
    ExtractedFact,
    ExtractionRun,
    FactEvidence,
    FactValidation,
    MilestoneEvent,
    MilestoneEvidence,
    MilestoneTechnology,
    ReviewAction,
    ReviewTask,
    SourceCollectionPolicy,
)
from app.modules.extraction.publish_gate import (
    PUBLISH_GATE_VERSION,
    compute_publish_score,
    route_publish_score,
)
from app.modules.job.models import (
    DataSource,
    EvidenceSpan,
    SourceDocument,
    SourceDocumentVersion,
)
from app.modules.taxonomy.models import TechnologyNode, TechnologyTaxonomyVersion


class DataCenterError(ValueError):
    """A user-correctable data-center contract violation."""


@dataclass(frozen=True)
class MilestoneSubmission:
    data_source_code: str
    source_record_key: str
    canonical_url: str
    title: str
    content_text: str
    published_at: datetime | None
    collected_at: datetime
    milestone_name: str
    milestone_type_code: str
    event_date: date | None
    event_year: int
    description_text: str
    maturity_delta_score: Decimal | None
    evidence_quote: str
    technology_codes: tuple[str, ...]
    extractor_code: str = "milestone-contract"
    extractor_version: str = "1.0.0"


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _code(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:20]}"


def create_collection_run(
    db: Session,
    *,
    source: DataSource,
    policy: SourceCollectionPolicy,
    scheduled_at: datetime | None = None,
) -> CollectionRun:
    if policy.data_source_id != source.data_source_id or not policy.is_active:
        raise DataCenterError("采集策略与数据源不匹配或已停用")
    run = CollectionRun(
        run_code=_code("CR"),
        data_source_id=source.data_source_id,
        collection_policy_id=policy.collection_policy_id,
        scheduled_at=scheduled_at,
        run_status_code="pending",
    )
    db.add(run)
    db.flush()
    return run


def record_collection_request(
    db: Session,
    *,
    run: CollectionRun,
    request_url: str,
    request_depth: int,
    request_type_code: str,
    parent_request_id: int | None = None,
) -> CollectionRequest:
    if request_depth not in {0, 1}:
        raise DataCenterError("采集请求只允许入口页和一层详情页")
    normalized = request_url.strip()
    existing = db.scalar(
        select(CollectionRequest).where(
            CollectionRequest.collection_run_id == run.collection_run_id,
            CollectionRequest.normalized_url_hash == _digest(normalized),
        )
    )
    if existing is not None:
        return existing
    request = CollectionRequest(
        collection_run_id=run.collection_run_id,
        parent_request_id=parent_request_id,
        request_url=normalized,
        normalized_url_hash=_digest(normalized),
        request_depth=request_depth,
        request_type_code=request_type_code,
    )
    db.add(request)
    db.flush()
    return request


def submit_milestone_candidate(db: Session, submission: MilestoneSubmission) -> MilestoneEvent:
    source = db.scalar(
        select(DataSource).where(
            DataSource.source_code == submission.data_source_code,
            DataSource.source_status_code == "active",
        )
    )
    if source is None:
        raise DataCenterError("数据源不存在或未启用")
    quote = submission.evidence_quote.strip()
    start_offset = submission.content_text.find(quote)
    if not quote or start_offset < 0:
        raise DataCenterError("证据原文必须是采集正文中的连续文本")
    if not 1900 <= submission.event_year <= 2200:
        raise DataCenterError("里程碑年份不在允许范围内")
    if submission.event_date and submission.event_date.year != submission.event_year:
        raise DataCenterError("事件日期与事件年份不一致")
    technology_codes = tuple(dict.fromkeys(code.strip() for code in submission.technology_codes))
    if not technology_codes:
        raise DataCenterError("里程碑至少关联一个标准技术词")
    active_versions = list(
        db.scalars(
            select(TechnologyTaxonomyVersion).where(
                TechnologyTaxonomyVersion.version_status_code == "active"
            )
        )
    )
    if len(active_versions) != 1:
        raise DataCenterError("系统必须且只能存在一个启用的技术体系版本")
    technologies = list(
        db.scalars(
            select(TechnologyNode).where(
                TechnologyNode.taxonomy_version_id == active_versions[0].taxonomy_version_id,
                TechnologyNode.technology_code.in_(technology_codes),
                TechnologyNode.governance_status_code == "active",
            )
        )
    )
    if {item.technology_code for item in technologies} != set(technology_codes):
        raise DataCenterError("存在未启用或不存在的标准技术词编码")
    document_version = _upsert_source_document(db, source, submission)
    normalized_value = _submission_snapshot(submission)
    fact_input_hash = _digest(
        f"{document_version.content_hash}:"
        + json.dumps(normalized_value, ensure_ascii=False, sort_keys=True)
    )
    existing = db.scalar(
        select(MilestoneEvent)
        .join(ExtractedFact, ExtractedFact.extracted_fact_id == MilestoneEvent.extracted_fact_id)
        .join(ExtractionRun, ExtractionRun.extraction_run_id == ExtractedFact.extraction_run_id)
        .where(
            ExtractionRun.source_document_version_id == document_version.source_document_version_id,
            ExtractionRun.input_hash == fact_input_hash,
        )
    )
    if existing is not None:
        return existing

    evidence_hash = _digest(quote)
    evidence = db.scalar(
        select(EvidenceSpan).where(
            EvidenceSpan.source_document_version_id == document_version.source_document_version_id,
            EvidenceSpan.evidence_hash == evidence_hash,
        )
    )
    if evidence is None:
        evidence = EvidenceSpan(
            source_document_version_id=document_version.source_document_version_id,
            span_type_code="milestone_claim",
            start_offset=start_offset,
            end_offset=start_offset + len(quote),
            evidence_text=quote,
            evidence_hash=evidence_hash,
            source_reliability_score=source.default_reliability_score,
        )
        db.add(evidence)
        db.flush()

    extraction_run = ExtractionRun(
        run_code=_code("ER"),
        source_document_version_id=document_version.source_document_version_id,
        extractor_code=submission.extractor_code,
        extractor_version=submission.extractor_version,
        input_hash=fact_input_hash,
    )
    db.add(extraction_run)
    db.flush()

    breakdown, publish_score = _milestone_score(source, submission, technologies)
    fact = ExtractedFact(
        extraction_run_id=extraction_run.extraction_run_id,
        fact_code=_code("FACT"),
        fact_type_code="milestone",
        normalized_value_json=normalized_value,
        extraction_confidence_score=Decimal(str(breakdown["extraction_confidence"])),
        publish_score=publish_score,
        fact_status_code="candidate",
    )
    db.add(fact)
    db.flush()
    db.add(
        FactEvidence(
            extracted_fact_id=fact.extracted_fact_id,
            evidence_span_id=evidence.evidence_span_id,
            support_score=Decimal("100"),
        )
    )
    db.add(
        FactValidation(
            extracted_fact_id=fact.extracted_fact_id,
            validator_code="milestone-rules-v1",
            validation_status_code="review_required",
            hard_error_count=0,
            score_breakdown_json=breakdown,
            reason_json={"codes": ["high_impact_fact_manual_review"]},
        )
    )

    milestone = MilestoneEvent(
        milestone_code=_code("MS"),
        extracted_fact_id=fact.extracted_fact_id,
        milestone_name=submission.milestone_name.strip(),
        milestone_type_code=submission.milestone_type_code,
        event_date=submission.event_date,
        event_year=submission.event_year,
        description_text=submission.description_text.strip(),
        maturity_delta_score=submission.maturity_delta_score,
    )
    db.add(milestone)
    db.flush()
    for technology in technologies:
        db.add(
            MilestoneTechnology(
                milestone_event_id=milestone.milestone_event_id,
                technology_node_id=technology.technology_node_id,
                relevance_score=Decimal("100"),
            )
        )
    db.add(
        MilestoneEvidence(
            milestone_event_id=milestone.milestone_event_id,
            evidence_span_id=evidence.evidence_span_id,
        )
    )
    snapshot = milestone_snapshot(db, milestone)
    priority = min(Decimal("100"), Decimal("130") - publish_score)
    db.add(
        ReviewTask(
            task_code=_code("RT"),
            queue_code="data_review",
            target_type_code="milestone",
            target_id=milestone.milestone_event_id,
            priority_score=priority,
            target_snapshot_json=snapshot,
            reason_json={
                "codes": ["high_impact_fact_manual_review"],
                "publish_score": str(publish_score),
            },
        )
    )
    db.flush()
    return milestone


def review_milestone(
    db: Session,
    *,
    task: ReviewTask,
    actor_user_id: int,
    action_code: str,
    comment_text: str | None = None,
) -> MilestoneEvent:
    transitions = {
        "claim": ({"queued"}, "reviewing"),
        "approve": ({"queued", "assigned", "reviewing", "needs_revision"}, "approved"),
        "reject": ({"queued", "assigned", "reviewing", "needs_revision"}, "rejected"),
        "needs_revision": ({"queued", "assigned", "reviewing"}, "needs_revision"),
    }
    if task.queue_code != "data_review" or task.target_type_code != "milestone":
        raise DataCenterError("审核任务不属于里程碑数据审核队列")
    if action_code not in transitions:
        raise DataCenterError("不支持的审核动作")
    allowed, target_status = transitions[action_code]
    if task.task_status_code not in allowed:
        raise DataCenterError("当前审核状态不允许执行该动作")
    milestone = db.get(MilestoneEvent, task.target_id)
    if milestone is None:
        raise DataCenterError("审核目标不存在")
    before = milestone_snapshot(db, milestone)
    from_status = task.task_status_code
    task.task_status_code = target_status
    task.assigned_user_id = actor_user_id
    if action_code == "approve":
        milestone.verification_status_code = "verified"
        milestone.verified_by_user_id = actor_user_id
        milestone.verified_at = datetime.now()
        fact = db.get(ExtractedFact, milestone.extracted_fact_id)
        if fact:
            fact.fact_status_code = "published"
        for relation in db.scalars(
            select(MilestoneTechnology).where(
                MilestoneTechnology.milestone_event_id == milestone.milestone_event_id
            )
        ):
            relation.is_human_confirmed = True
    elif action_code == "reject":
        milestone.verification_status_code = "rejected"
        fact = db.get(ExtractedFact, milestone.extracted_fact_id)
        if fact:
            fact.fact_status_code = "rejected"
    elif action_code == "needs_revision":
        milestone.verification_status_code = "needs_revision"
    db.flush()
    after = milestone_snapshot(db, milestone)
    db.add(
        ReviewAction(
            review_task_id=task.review_task_id,
            actor_user_id=actor_user_id,
            action_code=action_code,
            from_status_code=from_status,
            to_status_code=target_status,
            comment_text=comment_text,
            before_snapshot_json=before,
            after_snapshot_json=after,
        )
    )
    db.flush()
    return milestone


def milestone_snapshot(db: Session, milestone: MilestoneEvent) -> dict[str, Any]:
    codes = list(
        db.scalars(
            select(TechnologyNode.technology_code)
            .join(
                MilestoneTechnology,
                MilestoneTechnology.technology_node_id == TechnologyNode.technology_node_id,
            )
            .where(MilestoneTechnology.milestone_event_id == milestone.milestone_event_id)
            .order_by(TechnologyNode.technology_code)
        )
    )
    return {
        "milestone_code": milestone.milestone_code,
        "milestone_name": milestone.milestone_name,
        "milestone_type_code": milestone.milestone_type_code,
        "event_date": milestone.event_date.isoformat() if milestone.event_date else None,
        "event_year": milestone.event_year,
        "description_text": milestone.description_text,
        "maturity_delta_score": (
            str(milestone.maturity_delta_score)
            if milestone.maturity_delta_score is not None
            else None
        ),
        "verification_status_code": milestone.verification_status_code,
        "technology_codes": codes,
    }


def _upsert_source_document(
    db: Session, source: DataSource, submission: MilestoneSubmission
) -> SourceDocumentVersion:
    identity = _digest(submission.source_record_key.strip() or submission.canonical_url.strip())
    document = db.scalar(
        select(SourceDocument).where(
            SourceDocument.data_source_id == source.data_source_id,
            SourceDocument.document_identity_key == identity,
        )
    )
    if document is None:
        document = SourceDocument(
            document_code=_code("DOC"),
            data_source_id=source.data_source_id,
            document_type_code="milestone_material",
            source_record_key=submission.source_record_key,
            canonical_url=submission.canonical_url,
            document_identity_key=identity,
            title=submission.title,
            first_seen_at=submission.collected_at,
            last_seen_at=submission.collected_at,
        )
        db.add(document)
        db.flush()
    else:
        document.last_seen_at = max(document.last_seen_at, submission.collected_at)
    content_hash = _digest(submission.content_text)
    current = db.scalar(
        select(SourceDocumentVersion).where(
            SourceDocumentVersion.source_document_id == document.source_document_id,
            SourceDocumentVersion.content_hash == content_hash,
        )
    )
    if current is not None:
        return current
    previous = db.scalar(
        select(SourceDocumentVersion)
        .where(
            SourceDocumentVersion.source_document_id == document.source_document_id,
            SourceDocumentVersion.is_current.is_(True),
        )
        .order_by(SourceDocumentVersion.version_no.desc())
    )
    if previous is not None:
        previous.is_current = False
        previous.valid_to = submission.collected_at
    version = SourceDocumentVersion(
        source_document_id=document.source_document_id,
        version_no=(previous.version_no + 1) if previous else 1,
        previous_version_id=previous.source_document_version_id if previous else None,
        published_at=submission.published_at,
        collected_at=submission.collected_at,
        source_collected_at=submission.collected_at,
        valid_from=submission.collected_at,
        content_text=submission.content_text,
        content_hash=content_hash,
        parser_version=submission.extractor_version,
    )
    db.add(version)
    db.flush()
    return version


def _milestone_score(
    source: DataSource,
    submission: MilestoneSubmission,
    technologies: list[TechnologyNode],
) -> tuple[dict[str, float], Decimal]:
    reliability = float(source.default_reliability_score or Decimal("60"))
    extraction = 95.0
    completeness = 100.0 if submission.event_date else 85.0
    evidence_coverage = 100.0
    cross_source = 0.0
    timeliness = 90.0 if submission.published_at else 65.0
    consistency = 100.0 if technologies else 0.0
    # 三类惩罚项（设计 §6.3）：日期与年份矛盾计入 contradiction；
    # 重复与幻觉惩罚在规则入口暂无信号，保留 0 并入库留痕。
    contradiction_penalty = (
        8.0
        if submission.event_date is not None and submission.event_date.year != submission.event_year
        else 0.0
    )
    penalties = {
        "duplicate_penalty": 0.0,
        "contradiction_penalty": contradiction_penalty,
        "hallucination_penalty": 0.0,
    }
    score = compute_publish_score(
        {
            "source_reliability": reliability,
            "extraction_confidence": extraction,
            "schema_completeness": completeness,
            "evidence_coverage": evidence_coverage,
            "cross_source_support": cross_source,
            "timeliness": timeliness,
            "consistency": consistency,
        },
        penalties,
    )
    route = route_publish_score(score, high_impact=True)
    breakdown = {
        "gate_version": PUBLISH_GATE_VERSION,
        "source_reliability": reliability,
        "extraction_confidence": extraction,
        "completeness": completeness,
        "evidence_coverage": evidence_coverage,
        "cross_source_confirmation": cross_source,
        "timeliness": timeliness,
        "consistency": consistency,
        "duplicate_penalty": penalties["duplicate_penalty"],
        "contradiction_penalty": penalties["contradiction_penalty"],
        "hallucination_penalty": penalties["hallucination_penalty"],
        "publish_route": route,
        "manual_review_required": True,
    }
    return breakdown, Decimal(str(score))


def _submission_snapshot(submission: MilestoneSubmission) -> dict[str, Any]:
    return {
        "milestone_name": submission.milestone_name,
        "milestone_type_code": submission.milestone_type_code,
        "event_date": submission.event_date.isoformat() if submission.event_date else None,
        "event_year": submission.event_year,
        "description_text": submission.description_text,
        "maturity_delta_score": (
            str(submission.maturity_delta_score)
            if submission.maturity_delta_score is not None
            else None
        ),
        "technology_codes": list(submission.technology_codes),
    }
