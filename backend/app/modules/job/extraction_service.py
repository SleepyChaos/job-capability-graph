"""技术词表面匹配抽取：JD 导入与词表换版重抽取共用同一份实现。

抽取原先内联在 `JobImportService` 里、只在 JD 导入时跑一次，词表升版后无法在既有
JD 上重跑。这里把「建匹配器 + 落 requirement/evidence」抽成独立单元，两条入口
（首次导入 / 换版重抽取）共用，避免两份逻辑漂移。

所有产出按 `taxonomy_version_id` 归属，同一份 JD 的多版抽取结果并存。
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.modules.extraction.technology import (
    TechnologyAliasMatcher,
    TechnologyHit,
    TechnologyPattern,
)
from app.modules.job.models import (
    EvidenceSpan,
    JobPosting,
    JobRequirement,
    JobRequirementEvidence,
    SourceDocumentVersion,
)
from app.modules.taxonomy.models import TechnologyAlias, TechnologyNode

BONUS_MARKERS = ("加分", "优先", "优先考虑", "最好", "bonus", "preferred")

EXTRACTION_METHOD_CODE = "exact_alias_aho_v1"


@dataclass(frozen=True)
class ExtractionCounts:
    requirement_count: int
    evidence_count: int


def build_alias_matcher(session: Session, taxonomy_version_id: int) -> TechnologyAliasMatcher:
    """按词表版本装配 Aho-Corasick 匹配器，只收 `is_matchable` 的 L4 别名。"""
    l4_node = aliased(TechnologyNode)
    l3_node = aliased(TechnologyNode)
    rows = session.execute(
        select(TechnologyAlias, l3_node.technology_node_id)
        .join(l4_node, l4_node.technology_node_id == TechnologyAlias.technology_node_id)
        .join(l3_node, l3_node.technology_node_id == l4_node.parent_technology_node_id)
        .where(
            l4_node.taxonomy_version_id == taxonomy_version_id,
            l4_node.level_code == "L4",
            l3_node.level_code == "L3",
            TechnologyAlias.is_matchable.is_(True),
        )
    ).all()
    patterns = [
        TechnologyPattern(
            alias_id=alias.technology_alias_id,
            normalized_alias=alias.normalized_alias,
            l3_technology_node_id=l3_id,
        )
        for alias, l3_id in rows
        if alias.normalized_alias
    ]
    return TechnologyAliasMatcher(patterns)


def requirement_type(text: str, hit: TechnologyHit) -> str:
    context = text[max(0, hit.start_offset - 30) : min(len(text), hit.end_offset + 30)].casefold()
    return "bonus" if any(marker in context for marker in BONUS_MARKERS) else "required"


def snippet(text: str, start: int, end: int, radius: int = 45) -> str:
    return text[max(0, start - radius) : min(len(text), end + radius)]


def extract_requirements(
    session: Session,
    *,
    job: JobPosting,
    document_version: SourceDocumentVersion,
    matcher: TechnologyAliasMatcher,
    taxonomy_version_id: int,
) -> ExtractionCounts:
    """对单份 JD 跑一次表面词匹配，写入该词表版本下的技术要求与证据。"""
    hits = matcher.find(job.jd_clean_text)
    grouped: dict[tuple[int, str], list[TechnologyHit]] = defaultdict(list)
    for hit in hits:
        grouped[(hit.l3_technology_node_id, requirement_type(job.jd_clean_text, hit))].append(hit)
    evidence_count = 0
    for requirement_no, ((technology_node_id, type_code), group_hits) in enumerate(
        sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])), start=1
    ):
        first_hit = group_hits[0]
        requirement = JobRequirement(
            job_posting_id=job.job_posting_id,
            taxonomy_version_id=taxonomy_version_id,
            requirement_no=requirement_no,
            requirement_type_code=type_code,
            raw_term=first_hit.matched_text,
            raw_text=snippet(job.jd_clean_text, first_hit.start_offset, first_hit.end_offset),
            technology_node_id=technology_node_id,
            mention_count=len(group_hits),
            mapping_method_code=EXTRACTION_METHOD_CODE,
            confidence_score=Decimal("95"),
        )
        session.add(requirement)
        session.flush()
        for hit in group_hits:
            evidence = _ensure_evidence_span(session, job, document_version, hit)
            session.add(
                JobRequirementEvidence(
                    job_requirement_id=requirement.job_requirement_id,
                    evidence_span_id=evidence.evidence_span_id,
                    matched_alias_id=hit.alias_id,
                    support_score=Decimal("95"),
                )
            )
            evidence_count += 1
    return ExtractionCounts(requirement_count=len(grouped), evidence_count=evidence_count)


def _ensure_evidence_span(
    session: Session,
    job: JobPosting,
    document_version: SourceDocumentVersion,
    hit: TechnologyHit,
) -> EvidenceSpan:
    """证据跨度按 (文档版本, 哈希) 唯一；重抽取命中同一别名的同一位置时直接复用。"""
    evidence_hash = hashlib.sha256(
        f"{hit.start_offset}\0{hit.end_offset}\0{hit.alias_id}".encode()
    ).hexdigest()
    existing = session.scalar(
        select(EvidenceSpan).where(
            EvidenceSpan.source_document_version_id
            == document_version.source_document_version_id,
            EvidenceSpan.evidence_hash == evidence_hash,
        )
    )
    if existing is not None:
        return existing
    evidence = EvidenceSpan(
        source_document_version_id=document_version.source_document_version_id,
        span_type_code="requirement",
        start_offset=hit.start_offset,
        end_offset=hit.end_offset,
        evidence_text=job.jd_clean_text[hit.start_offset : hit.end_offset],
        evidence_hash=evidence_hash,
        source_reliability_score=Decimal("95"),
    )
    session.add(evidence)
    session.flush()
    return evidence
