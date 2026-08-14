from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.modules.extraction.job_structure import (
    JobStructureParser,
    ParsedJobSegment,
    cluster_tokens,
    task_parts,
)
from app.modules.job.models import (
    EvidenceSpan,
    JobClusterFeatureSnapshot,
    JobFactEvidence,
    JobParseResult,
    JobParseRun,
    JobPosting,
    JobRequirement,
    JobRequirementEvidence,
    JobResponsibility,
    JobScenario,
    SourceDocumentVersion,
    TechnologyAmbiguityRule,
    TechnologyMatchAssessment,
)
from app.modules.job.service import stable_code
from app.modules.taxonomy.models import (
    TechnologyAlias,
    TechnologyDomain,
    TechnologyNode,
    TechnologyNodeDomain,
    TechnologyTaxonomyVersion,
)

PARSER_VERSION = "jd_structure_rules_v1"
FEATURE_VERSION = "cluster_features_v1"
AMBIGUITY_RULE_VERSION = "technology_context_rules_v1"

AMBIGUITY_RULE_DEFINITIONS = {
    ("检测", "T6.03.04"): (
        "ambiguity_detection_certification",
        ["认证", "检验", "质检", "质量", "可靠性", "安规", "标准", "inspection"],
    ),
    ("汽车", "T7.01.04"): (
        "ambiguity_automotive_manufacturing",
        ["制造", "产线", "装配", "工厂", "生产", "焊接", "车身", "manufacturing"],
    ),
    ("大模型", "T1.01.11"): (
        "ambiguity_vla_large_model",
        [
            "具身",
            "机器人",
            "vla",
            "视觉语言动作",
            "vision-language-action",
            "端到端",
            "多模态",
        ],
    ),
    ("控制系统", "T1.03.12"): (
        "ambiguity_motion_control_system",
        ["机器人", "运动", "实时", "伺服", "plc", "嵌入式", "执行器", "关节"],
    ),
}


@dataclass(frozen=True)
class JobParsingResult:
    run_code: str
    input_job_count: int
    parsed_job_count: int
    review_job_count: int
    responsibility_count: int
    assessment_count: int
    ambiguity_review_count: int
    feature_count: int
    eligible_feature_count: int
    already_completed: bool


class JobParsingError(ValueError):
    pass


class JobParsingService:
    def __init__(self, session: Session):
        self.session = session
        self.parser = JobStructureParser()

    def run(
        self,
        *,
        taxonomy_version_code: str,
        target_date: date,
        parser_version: str = PARSER_VERSION,
    ) -> JobParsingResult:
        taxonomy = self.session.scalar(
            select(TechnologyTaxonomyVersion).where(
                TechnologyTaxonomyVersion.version_code == taxonomy_version_code,
                TechnologyTaxonomyVersion.version_status_code == "active",
            )
        )
        if taxonomy is None:
            raise JobParsingError(f"技术体系版本不可用：{taxonomy_version_code}")
        jobs = list(
            self.session.scalars(
                select(JobPosting)
                .where(
                    or_(
                        and_(
                            JobPosting.source_collected_at.is_not(None),
                            func.date(JobPosting.source_collected_at) <= target_date.isoformat(),
                        ),
                        and_(
                            JobPosting.source_collected_at.is_(None),
                            func.date(JobPosting.collected_at) <= target_date.isoformat(),
                        ),
                    )
                )
                .order_by(JobPosting.job_posting_id)
            )
        )
        if not jobs:
            raise JobParsingError("目标日期前没有可解析JD")
        versions = {
            item.source_document_version_id: item
            for item in self.session.scalars(
                select(SourceDocumentVersion).where(
                    SourceDocumentVersion.source_document_version_id.in_(
                        [job.source_document_version_id for job in jobs]
                    )
                )
            )
        }
        snapshot_hash = self._snapshot_hash(jobs, versions, parser_version, target_date)
        run_code = stable_code(
            "jdparse",
            f"{taxonomy.taxonomy_version_id}\0{parser_version}\0{target_date}\0{snapshot_hash}",
        )
        existing = self.session.scalar(select(JobParseRun).where(JobParseRun.run_code == run_code))
        if existing is not None:
            if existing.run_status_code != "completed":
                raise JobParsingError(f"解析运行{run_code}处于{existing.run_status_code}状态")
            return self._result(existing, already_completed=True)

        run = JobParseRun(
            run_code=run_code,
            parser_version=parser_version,
            taxonomy_version_id=taxonomy.taxonomy_version_id,
            target_date=target_date,
            input_snapshot_hash=snapshot_hash,
            config_json={
                "feature_version": FEATURE_VERSION,
                "ambiguity_rule_version": AMBIGUITY_RULE_VERSION,
                "ambiguity_rule_count": len(AMBIGUITY_RULE_DEFINITIONS),
            },
            input_job_count=len(jobs),
        )
        self.session.add(run)
        self.session.flush()
        ambiguity_rules = self._ensure_ambiguity_rules(taxonomy.taxonomy_version_id)
        requirement_rows = self._load_requirement_rows(jobs)
        domain_map = self._load_domain_map(taxonomy.taxonomy_version_id)

        total_responsibilities = 0
        total_assessments = 0
        total_ambiguity_reviews = 0
        review_jobs = 0
        eligible_features = 0
        for job in jobs:
            version = versions[job.source_document_version_id]
            segments = self.parser.parse(job.jd_clean_text)
            relevant_segments = [
                item
                for item in segments
                if item.segment_type in {"responsibility", "required", "bonus"}
            ]
            responsibility_segments = [
                item for item in relevant_segments if item.segment_type == "responsibility"
            ]
            context_evidence: dict[tuple[int, int, str], EvidenceSpan] = {}
            responsibilities = self._create_responsibilities(
                run,
                job,
                version,
                responsibility_segments,
                context_evidence,
            )
            self._create_scenarios(
                run, job, [item for item in segments if item.segment_type == "scenario"]
            )
            assessments, ambiguity_review_count = self._assess_technologies(
                run,
                job,
                version,
                segments,
                requirement_rows.get(job.job_posting_id, []),
                ambiguity_rules,
                context_evidence,
            )
            total_responsibilities += len(responsibilities)
            total_assessments += len(assessments)
            total_ambiguity_reviews += ambiguity_review_count
            required_count = sum(item.segment_type == "required" for item in relevant_segments)
            bonus_count = sum(item.segment_type == "bonus" for item in relevant_segments)
            unknown_count = sum(item.segment_type == "unknown" for item in segments)
            quality_score = self._quality_score(
                len(responsibilities), required_count + bonus_count, unknown_count, len(segments)
            )
            reasons: list[str] = []
            if not responsibilities:
                reasons.append("missing_responsibility")
            if ambiguity_review_count:
                reasons.append("ambiguous_technology_match")
            if segments and unknown_count / len(segments) > 0.7:
                reasons.append("high_unknown_segment_ratio")
            review_required = bool(reasons)
            if review_required:
                review_jobs += 1
            self.session.add(
                JobParseResult(
                    job_parse_run_id=run.job_parse_run_id,
                    job_posting_id=job.job_posting_id,
                    source_document_version_id=version.source_document_version_id,
                    content_hash=version.content_hash,
                    parse_status_code="needs_review" if review_required else "parsed",
                    responsibility_count=len(responsibilities),
                    required_segment_count=required_count,
                    bonus_segment_count=bonus_count,
                    unknown_segment_count=unknown_count,
                    ambiguity_review_count=ambiguity_review_count,
                    parse_quality_score=quality_score,
                    review_required=review_required,
                    reason_json={"reasons": reasons},
                )
            )
            feature = self._create_feature(
                run,
                job,
                responsibilities,
                requirement_rows.get(job.job_posting_id, []),
                assessments,
                domain_map,
                quality_score,
            )
            self.session.add(feature)
            if feature.eligible_for_clustering:
                eligible_features += 1

        run.run_status_code = "completed"
        run.parsed_job_count = len(jobs)
        run.review_job_count = review_jobs
        run.responsibility_count = total_responsibilities
        run.assessment_count = total_assessments
        run.feature_count = len(jobs)
        run.completed_at = datetime.now()
        self.session.commit()
        result = self._result(run, already_completed=False)
        return JobParsingResult(
            **{
                **result.__dict__,
                "ambiguity_review_count": total_ambiguity_reviews,
                "eligible_feature_count": eligible_features,
            }
        )

    def _ensure_ambiguity_rules(
        self, taxonomy_version_id: int
    ) -> dict[tuple[str, int], TechnologyAmbiguityRule]:
        nodes = {
            node.technology_code: node
            for node in self.session.scalars(
                select(TechnologyNode).where(
                    TechnologyNode.taxonomy_version_id == taxonomy_version_id,
                    TechnologyNode.level_code == "L3",
                )
            )
        }
        result: dict[tuple[str, int], TechnologyAmbiguityRule] = {}
        for (alias, technology_code), (
            rule_code,
            positive_markers,
        ) in AMBIGUITY_RULE_DEFINITIONS.items():
            node = nodes.get(technology_code)
            if node is None:
                raise JobParsingError(f"歧义规则引用的技术点不存在：{technology_code}")
            rule = self.session.scalar(
                select(TechnologyAmbiguityRule).where(
                    TechnologyAmbiguityRule.normalized_alias == alias,
                    TechnologyAmbiguityRule.technology_node_id == node.technology_node_id,
                )
            )
            if rule is None:
                rule = TechnologyAmbiguityRule(
                    rule_code=rule_code,
                    normalized_alias=alias,
                    technology_node_id=node.technology_node_id,
                    positive_markers_json=positive_markers,
                    missing_context_decision_code="needs_review",
                    review_weight=Decimal("0.35"),
                    rule_version=AMBIGUITY_RULE_VERSION,
                )
                self.session.add(rule)
                self.session.flush()
            result[(alias, node.technology_node_id)] = rule
        return result

    def _load_requirement_rows(self, jobs: list[JobPosting]) -> dict[int, list[tuple]]:
        grouped: dict[int, list[tuple]] = defaultdict(list)
        rows = self.session.execute(
            select(
                JobRequirement,
                JobRequirementEvidence,
                EvidenceSpan,
                TechnologyAlias,
                TechnologyNode,
            )
            .join(
                JobRequirementEvidence,
                JobRequirementEvidence.job_requirement_id == JobRequirement.job_requirement_id,
            )
            .join(
                EvidenceSpan,
                EvidenceSpan.evidence_span_id == JobRequirementEvidence.evidence_span_id,
            )
            .join(
                TechnologyAlias,
                TechnologyAlias.technology_alias_id == JobRequirementEvidence.matched_alias_id,
            )
            .join(
                TechnologyNode,
                TechnologyNode.technology_node_id == JobRequirement.technology_node_id,
            )
            .where(JobRequirement.job_posting_id.in_([job.job_posting_id for job in jobs]))
            .order_by(JobRequirement.job_posting_id, EvidenceSpan.start_offset)
        ).all()
        for row in rows:
            grouped[row[0].job_posting_id].append(row)
        return grouped

    def _load_domain_map(self, taxonomy_version_id: int) -> dict[int, list[tuple[str, Decimal]]]:
        grouped: dict[int, list[tuple[str, Decimal]]] = defaultdict(list)
        for technology_id, domain_code, score in self.session.execute(
            select(
                TechnologyNodeDomain.technology_node_id,
                TechnologyDomain.domain_code,
                TechnologyNodeDomain.domain_score,
            )
            .join(
                TechnologyDomain,
                TechnologyDomain.technology_domain_id == TechnologyNodeDomain.technology_domain_id,
            )
            .join(
                TechnologyNode,
                TechnologyNode.technology_node_id == TechnologyNodeDomain.technology_node_id,
            )
            .where(
                TechnologyNode.taxonomy_version_id == taxonomy_version_id,
                TechnologyNode.level_code == "L3",
                TechnologyNodeDomain.review_status_code == "confirmed",
            )
        ).all():
            grouped[technology_id].append((domain_code, score))
        return grouped

    def _create_responsibilities(
        self,
        run: JobParseRun,
        job: JobPosting,
        version: SourceDocumentVersion,
        segments: list[ParsedJobSegment],
        context_evidence: dict[tuple[int, int, str], EvidenceSpan],
    ) -> list[JobResponsibility]:
        result: list[JobResponsibility] = []
        for number, segment in enumerate(segments, start=1):
            action, task_object, expected = task_parts(segment.text)
            responsibility = JobResponsibility(
                job_parse_run_id=run.job_parse_run_id,
                job_posting_id=job.job_posting_id,
                responsibility_no=number,
                raw_text=segment.text,
                normalized_task_text=task_object,
                action_verb=action,
                task_object=task_object,
                expected_output=expected,
                extraction_method_code=PARSER_VERSION,
                confidence_score=Decimal(segment.confidence),
            )
            self.session.add(responsibility)
            self.session.flush()
            evidence = self._context_evidence(
                run, version, segment, context_evidence, span_type="responsibility"
            )
            self.session.add(
                JobFactEvidence(
                    job_parse_run_id=run.job_parse_run_id,
                    job_posting_id=job.job_posting_id,
                    target_type_code="responsibility",
                    target_id=responsibility.job_responsibility_id,
                    evidence_span_id=evidence.evidence_span_id,
                    support_type_code="support",
                    support_score=Decimal(segment.confidence),
                )
            )
            result.append(responsibility)
        return result

    def _create_scenarios(
        self, run: JobParseRun, job: JobPosting, segments: list[ParsedJobSegment]
    ) -> None:
        """设计 §7.1：把 JD 中的应用场景段落写入 rel_job_scenario（最多保留 6 条）。"""
        for number, segment in enumerate(segments[:6], start=1):
            self.session.add(
                JobScenario(
                    job_parse_run_id=run.job_parse_run_id,
                    job_posting_id=job.job_posting_id,
                    scenario_no=number,
                    scenario_text=segment.text[:2000],
                    normalized_scenario=" ".join(segment.text.split())[:500],
                    start_offset=segment.start_offset,
                    end_offset=segment.end_offset,
                    confidence_score=Decimal(segment.confidence),
                    data_origin_code="source_fact",
                )
            )

    def _assess_technologies(
        self,
        run: JobParseRun,
        job: JobPosting,
        version: SourceDocumentVersion,
        segments: list[ParsedJobSegment],
        requirement_rows: list[tuple],
        rules: dict[tuple[str, int], TechnologyAmbiguityRule],
        context_evidence: dict[tuple[int, int, str], EvidenceSpan],
    ) -> tuple[list[TechnologyMatchAssessment], int]:
        result: list[TechnologyMatchAssessment] = []
        review_count = 0
        for requirement, _relation, evidence, alias, technology in requirement_rows:
            segment = self._containing_segment(segments, evidence)
            context_type = segment.segment_type if segment else requirement.requirement_type_code
            context_text = (
                segment.text
                if segment
                else job.jd_clean_text[
                    max(0, (evidence.start_offset or 0) - 100) : min(
                        len(job.jd_clean_text), (evidence.end_offset or 0) + 100
                    )
                ]
            )
            rule = rules.get((alias.normalized_alias, technology.technology_node_id))
            if rule is None:
                status = "accepted"
                score = Decimal("95")
                feature_weight = Decimal("1")
                reason = "exact_alias"
            elif any(
                marker.casefold() in context_text.casefold()
                for marker in rule.positive_markers_json
            ):
                status = "accepted"
                score = Decimal("80")
                feature_weight = Decimal("0.85")
                reason = "ambiguity_context_confirmed"
            else:
                status = rule.missing_context_decision_code
                score = Decimal("35")
                feature_weight = rule.review_weight
                reason = "ambiguity_context_missing"
                review_count += 1
            context_span = (
                self._context_evidence(
                    run, version, segment, context_evidence, span_type="requirement_context"
                )
                if segment
                else None
            )
            assessment = TechnologyMatchAssessment(
                job_parse_run_id=run.job_parse_run_id,
                job_requirement_id=requirement.job_requirement_id,
                evidence_span_id=evidence.evidence_span_id,
                context_evidence_span_id=(context_span.evidence_span_id if context_span else None),
                ambiguity_rule_id=(rule.technology_ambiguity_rule_id if rule else None),
                context_type_code=context_type,
                assessment_status_code=status,
                adjusted_support_score=score,
                feature_weight=feature_weight,
                reason_code=reason,
            )
            self.session.add(assessment)
            result.append(assessment)
        return result, review_count

    def _create_feature(
        self,
        run: JobParseRun,
        job: JobPosting,
        responsibilities: list[JobResponsibility],
        requirement_rows: list[tuple],
        assessments: list[TechnologyMatchAssessment],
        domain_map: dict[int, list[tuple[str, Decimal]]],
        quality_score: Decimal,
    ) -> JobClusterFeatureSnapshot:
        assessment_by_evidence = {item.evidence_span_id: item for item in assessments}
        requirement_weights: dict[int, Decimal] = defaultdict(Decimal)
        technology_code_by_id: dict[int, str] = {}
        for requirement, _relation, evidence, _alias, technology in requirement_rows:
            assessment = assessment_by_evidence[evidence.evidence_span_id]
            type_weight = (
                Decimal("0.70") if assessment.context_type_code == "bonus" else Decimal("1")
            )
            evidence_weight = type_weight * assessment.feature_weight
            requirement_weights[requirement.job_requirement_id] = max(
                requirement_weights[requirement.job_requirement_id], evidence_weight
            )
            technology_code_by_id[technology.technology_node_id] = technology.technology_code
        technology_weights: dict[str, Decimal] = defaultdict(Decimal)
        technology_ids_by_requirement: dict[int, int] = {}
        for requirement, *_rest, technology in requirement_rows:
            if requirement.technology_node_id is not None:
                technology_ids_by_requirement[requirement.job_requirement_id] = (
                    requirement.technology_node_id
                )
                technology_weights[technology.technology_code] = max(
                    technology_weights[technology.technology_code],
                    requirement_weights[requirement.job_requirement_id],
                )
        domain_weights: dict[str, Decimal] = defaultdict(Decimal)
        for requirement_id, technology_id in technology_ids_by_requirement.items():
            weight = requirement_weights[requirement_id]
            for domain_code, domain_score in domain_map.get(technology_id, []):
                domain_weights[domain_code] += weight * domain_score / Decimal("100")
        responsibility_tokens = cluster_tokens(
            " ".join(item.normalized_task_text or item.raw_text for item in responsibilities)
        )
        title_tokens = cluster_tokens(job.job_title_normalized)
        exclusions: list[str] = []
        if not responsibilities and not technology_weights:
            exclusions.append("no_structured_cluster_signal")
        if quality_score < Decimal("25"):
            exclusions.append("parse_quality_too_low")
        payload = {
            "title_tokens": title_tokens,
            "responsibility_tokens": responsibility_tokens,
            "technology_weights": {
                key: float(value.quantize(Decimal("0.0001")))
                for key, value in sorted(technology_weights.items())
            },
            "domain_weights": {
                key: float(value.quantize(Decimal("0.0001")))
                for key, value in sorted(domain_weights.items())
            },
            "level_code": job.job_level_code,
            "sample_weight": float(job.evidence_weight),
            "time_quality_code": job.time_quality_code,
        }
        feature_hash = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        return JobClusterFeatureSnapshot(
            job_parse_run_id=run.job_parse_run_id,
            job_posting_id=job.job_posting_id,
            feature_version=FEATURE_VERSION,
            title_tokens_json=title_tokens,
            responsibility_tokens_json=responsibility_tokens,
            technology_weights_json=payload["technology_weights"],
            domain_weights_json=payload["domain_weights"],
            level_code=job.job_level_code,
            sample_weight=job.evidence_weight,
            time_quality_code=job.time_quality_code,
            feature_hash=feature_hash,
            eligible_for_clustering=not exclusions,
            exclusion_reason_json=exclusions,
        )

    def _context_evidence(
        self,
        run: JobParseRun,
        version: SourceDocumentVersion,
        segment: ParsedJobSegment,
        cache: dict[tuple[int, int, str], EvidenceSpan],
        *,
        span_type: str,
    ) -> EvidenceSpan:
        key = (segment.start_offset, segment.end_offset, span_type)
        existing = cache.get(key)
        if existing is not None:
            return existing
        evidence_hash = hashlib.sha256(
            f"{run.run_code}\0{span_type}\0{segment.start_offset}\0{segment.end_offset}".encode()
        ).hexdigest()
        evidence = EvidenceSpan(
            source_document_version_id=version.source_document_version_id,
            span_type_code=span_type,
            start_offset=segment.start_offset,
            end_offset=segment.end_offset,
            evidence_text=segment.text,
            evidence_hash=evidence_hash,
            source_reliability_score=Decimal(segment.confidence),
        )
        self.session.add(evidence)
        self.session.flush()
        cache[key] = evidence
        return evidence

    @staticmethod
    def _containing_segment(
        segments: list[ParsedJobSegment], evidence: EvidenceSpan
    ) -> ParsedJobSegment | None:
        if evidence.start_offset is None or evidence.end_offset is None:
            return None
        candidates = [
            item
            for item in segments
            if item.start_offset <= evidence.start_offset and evidence.end_offset <= item.end_offset
        ]
        return (
            min(candidates, key=lambda item: item.end_offset - item.start_offset)
            if candidates
            else None
        )

    @staticmethod
    def _quality_score(
        responsibility_count: int,
        requirement_segment_count: int,
        unknown_count: int,
        total_segments: int,
    ) -> Decimal:
        responsibility_score = min(Decimal("40"), Decimal("20") + responsibility_count * 5)
        if responsibility_count == 0:
            responsibility_score = Decimal("0")
        requirement_score = min(Decimal("30"), Decimal(requirement_segment_count * 6))
        known_ratio = (
            Decimal(total_segments - unknown_count) / Decimal(total_segments)
            if total_segments
            else Decimal("0")
        )
        return (responsibility_score + requirement_score + known_ratio * Decimal("30")).quantize(
            Decimal("0.01")
        )

    @staticmethod
    def _snapshot_hash(
        jobs: list[JobPosting],
        versions: dict[int, SourceDocumentVersion],
        parser_version: str,
        target_date: date,
    ) -> str:
        digest = hashlib.sha256(f"{parser_version}\0{target_date}".encode())
        for job in jobs:
            digest.update(
                f"\0{job.job_code}\0{versions[job.source_document_version_id].content_hash}".encode()
            )
        return digest.hexdigest()

    def _result(self, run: JobParseRun, *, already_completed: bool) -> JobParsingResult:
        ambiguity_review_count = (
            self.session.scalar(
                select(func.count())
                .select_from(TechnologyMatchAssessment)
                .where(
                    TechnologyMatchAssessment.job_parse_run_id == run.job_parse_run_id,
                    TechnologyMatchAssessment.assessment_status_code == "needs_review",
                )
            )
            or 0
        )
        eligible_feature_count = (
            self.session.scalar(
                select(func.count())
                .select_from(JobClusterFeatureSnapshot)
                .where(
                    JobClusterFeatureSnapshot.job_parse_run_id == run.job_parse_run_id,
                    JobClusterFeatureSnapshot.eligible_for_clustering.is_(True),
                )
            )
            or 0
        )
        return JobParsingResult(
            run_code=run.run_code,
            input_job_count=run.input_job_count,
            parsed_job_count=run.parsed_job_count,
            review_job_count=run.review_job_count,
            responsibility_count=run.responsibility_count,
            assessment_count=run.assessment_count,
            ambiguity_review_count=ambiguity_review_count,
            feature_count=run.feature_count,
            eligible_feature_count=eligible_feature_count,
            already_completed=already_completed,
        )
