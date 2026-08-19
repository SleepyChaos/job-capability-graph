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
# v2（窗口 C-5）相对 v1 的三处变化：
# 1. 语境窗口从「整个段落」收紧到「命中词所在的句子」——同段共现不再构成证据；
# 2. 正向语境词带权重，需累计 ≥1.0 才放行，高频泛触发词（机器人/多模态）降权；
# 3. 「检测/汽车/大模型」三条规则退场：这些词在 v1.2 词表里已被下线或改词形，
#    不再需要靠语境兜底（实测语境放行路径对它们几乎全是误报）。
AMBIGUITY_RULE_VERSION = "technology_context_rules_v2"

# 语境词权重口径：1.0 = 单独出现即可放行；0.5 = 需与另一个词同句共现；
# 权重依据为窗口 A-1 的《过宽表面词排查报告》第 4 节触发频次与 LLM 复核接受率。
AMBIGUITY_RULE_DEFINITIONS: dict[tuple[str, str], tuple[str, list[tuple[str, float]]]] = {
    ("控制系统", "T1.03.12"): (
        "ambiguity_motion_control_system",
        [
            # 「机器人」单独触发了 38/91 次而 LLM 只接受 2/24，降为半权。
            ("机器人", 0.5),
            ("运动控制", 1.0),
            ("伺服", 1.0),
            ("关节", 1.0),
            ("执行器", 1.0),
            ("plc", 1.0),
            ("嵌入式", 0.5),
            ("实时", 0.5),
            ("运动", 0.5),
        ],
    ),
    ("多模态大模型", "T1.01.11"): (
        "ambiguity_multimodal_vla",
        [
            ("具身", 1.0),
            ("vla", 1.0),
            ("视觉语言动作", 1.0),
            ("机械臂", 1.0),
            ("抓取", 1.0),
            # 「机器人」「多模态」在 v1 里是主要误放行来源，降为半权。
            ("机器人", 0.5),
            ("动作", 0.5),
            ("操作", 0.5),
            ("端到端", 0.5),
        ],
    ),
    ("基础模型", "T1.01.11"): (
        "ambiguity_foundation_model_vla",
        [
            ("具身", 1.0),
            ("vla", 1.0),
            ("机器人", 0.5),
            ("动作", 0.5),
            ("操作", 0.5),
            ("端到端", 0.5),
        ],
    ),
}

# 句子切分：中英文句读 + 换行 + 分号；用于把语境窗口限制在命中词所在句。
SENTENCE_BOUNDARIES = frozenset("。！？；!?;\n\r")
# 语境词权重累计到该阈值才放行；1.0 = 一个强词或两个弱词。
MARKER_WEIGHT_THRESHOLD = 1.0
# 句子过长时（招聘文案常整段无句读）限制语境窗口，避免退化回段落口径。
MAX_SENTENCE_RADIUS = 60


def sentence_around(text: str, start: int, end: int) -> str:
    """取命中词所在句子；无句读时退回命中词左右各 MAX_SENTENCE_RADIUS 字符。"""
    left = start
    while left > 0 and text[left - 1] not in SENTENCE_BOUNDARIES:
        if start - left >= MAX_SENTENCE_RADIUS:
            break
        left -= 1
    right = end
    while right < len(text) and text[right] not in SENTENCE_BOUNDARIES:
        if right - end >= MAX_SENTENCE_RADIUS:
            break
        right += 1
    return text[left:right]


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
            f"{taxonomy.taxonomy_version_id}\0{parser_version}\0{AMBIGUITY_RULE_VERSION}"
            f"\0{target_date}\0{snapshot_hash}",
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
        ambiguity_rules = self._ensure_ambiguity_rules(taxonomy)
        requirement_rows = self._load_requirement_rows(jobs, taxonomy.taxonomy_version_id)
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
        self, taxonomy: TechnologyTaxonomyVersion
    ) -> dict[tuple[str, int], TechnologyAmbiguityRule]:
        """按词表版本落规则行。

        规则挂在具体的 `technology_node_id` 上，而节点是逐版本独立的，因此每个词表版本
        都有自己的一套规则行；`rule_code` 里带版本后缀，避免跨版本撞唯一键。
        """
        nodes = {
            node.technology_code: node
            for node in self.session.scalars(
                select(TechnologyNode).where(
                    TechnologyNode.taxonomy_version_id == taxonomy.taxonomy_version_id,
                    TechnologyNode.level_code == "L3",
                )
            )
        }
        result: dict[tuple[str, int], TechnologyAmbiguityRule] = {}
        active_rule_ids: set[int] = set()
        for (alias, technology_code), (
            rule_code,
            positive_markers,
        ) in AMBIGUITY_RULE_DEFINITIONS.items():
            node = nodes.get(technology_code)
            if node is None:
                raise JobParsingError(f"歧义规则引用的技术点不存在：{technology_code}")
            markers_payload = [
                {"term": term, "weight": weight} for term, weight in positive_markers
            ]
            versioned_code = f"{rule_code}@{taxonomy.version_code}"
            rule = self.session.scalar(
                select(TechnologyAmbiguityRule).where(
                    TechnologyAmbiguityRule.normalized_alias == alias,
                    TechnologyAmbiguityRule.technology_node_id == node.technology_node_id,
                )
            )
            if rule is None:
                rule = TechnologyAmbiguityRule(
                    rule_code=versioned_code,
                    normalized_alias=alias,
                    technology_node_id=node.technology_node_id,
                    positive_markers_json=markers_payload,
                    missing_context_decision_code="needs_review",
                    review_weight=Decimal("0.35"),
                    rule_version=AMBIGUITY_RULE_VERSION,
                )
                self.session.add(rule)
                self.session.flush()
            elif (
                rule.rule_version != AMBIGUITY_RULE_VERSION or rule.rule_code != versioned_code
            ):
                # 规则升版必须就地刷新，否则旧版语境词会被继续沿用。
                rule.rule_code = versioned_code
                rule.positive_markers_json = markers_payload
                rule.rule_version = AMBIGUITY_RULE_VERSION
                rule.is_active = True
                self.session.flush()
            active_rule_ids.add(rule.technology_ambiguity_rule_id)
            result[(alias, node.technology_node_id)] = rule
        # 本版已退场的规则停用（不删行，历史运行仍能通过 ambiguity_rule_id 回溯口径）。
        # 只处理本词表版本自己的规则行，别把其它版本的规则一起关掉。
        version_node_ids = [node.technology_node_id for node in nodes.values()]
        for stale in self.session.scalars(
            select(TechnologyAmbiguityRule).where(
                TechnologyAmbiguityRule.is_active.is_(True),
                TechnologyAmbiguityRule.technology_node_id.in_(version_node_ids or [-1]),
                TechnologyAmbiguityRule.technology_ambiguity_rule_id.notin_(
                    active_rule_ids or {-1}
                ),
            )
        ):
            stale.is_active = False
        self.session.flush()
        return result

    def _load_requirement_rows(
        self, jobs: list[JobPosting], taxonomy_version_id: int
    ) -> dict[int, list[tuple]]:
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
            .where(
                JobRequirement.job_posting_id.in_([job.job_posting_id for job in jobs]),
                # 同一份 JD 可能存有多版词表的抽取结果，只读本次解析所用的那一版。
                JobRequirement.taxonomy_version_id == taxonomy_version_id,
            )
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
            rule = rules.get((alias.normalized_alias, technology.technology_node_id))
            if rule is None:
                status = "accepted"
                score = Decimal("95")
                feature_weight = Decimal("1")
                reason = "exact_alias"
            elif (
                self._marker_weight(
                    sentence_around(job.jd_clean_text, evidence.start_offset, evidence.end_offset),
                    rule.positive_markers_json,
                )
                >= MARKER_WEIGHT_THRESHOLD
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

    @staticmethod
    def _marker_weight(sentence: str, markers: list) -> float:
        """累计同句出现的正向语境词权重。

        v1 只要整段里出现任一语境词就放行，实测「机器人」一个泛词就放行了大量销售/
        产品岗；v2 要求语境词与命中词同句，并按权重累计到阈值才算证据。
        """
        lowered = sentence.casefold()
        total = 0.0
        for marker in markers:
            if isinstance(marker, dict):
                term = str(marker.get("term", ""))
                weight = float(marker.get("weight", 1.0))
            else:  # 兼容 v1 遗留的纯字符串列表
                term = str(marker)
                weight = 1.0
            if term and term.casefold() in lowered:
                total += weight
        return total

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
