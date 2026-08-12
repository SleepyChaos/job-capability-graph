import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from itertools import combinations
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.clustering.models import (
    JobClusteringRun,
    JobRole,
    JobRoleAlias,
    JobRoleVersion,
    JobRoleVersionRequirement,
)
from app.modules.data_center.models import (
    MilestoneEvent,
    MilestoneEvidence,
    MilestoneTechnology,
    ReviewAction,
    ReviewTask,
)
from app.modules.discovery.algorithm import (
    CandidateSignals,
    MaturityEventSignal,
    calculate_market_support,
    calculate_maturity,
    calculate_task_gap,
    score_candidate,
)
from app.modules.discovery.models import (
    CandidateScoreComponent,
    CandidateTechnology,
    DiscoveryRun,
    EmergingRoleCandidate,
    IndustryTask,
    IndustryTaskEvidence,
    IndustryTaskTechnology,
    MaturityEventContribution,
    StandardJobDescription,
    TaskCommunity,
    TaskCommunityMember,
    TechnologyMaturitySnapshot,
)
from app.modules.job.models import (
    EvidenceSpan,
    JobPosting,
    JobPostingDataSource,
    JobRequirement,
    JobResponsibility,
    TechnologyMatchAssessment,
)
from app.modules.taxonomy.models import TechnologyNode, TechnologyTaxonomyVersion

ALGORITHM_VERSION = "evidence_gap_discovery_v1_1"
DEFAULT_PARAMETERS = {
    "min_pair_job_count": 2,
    "max_communities": 100,
    "exploration_floor": 0.15,
}


class DiscoveryError(ValueError):
    """A user-correctable discovery workflow error."""


@dataclass(frozen=True)
class DiscoveryResult:
    run_code: str
    candidate_count: int
    task_count: int
    evidence_limited: bool
    already_completed: bool = False


@dataclass
class _PairEvidence:
    job_ids: set[int]
    organization_ids: set[int]
    source_ids: set[int]
    observation_windows: set[str]
    responsibilities: list[JobResponsibility]
    evidence_job_ids: dict[int, int]


def run_discovery(
    db: Session,
    *,
    mode_code: str,
    target_date: date,
    selected_technology_ids: list[int] | None = None,
    query_role_name: str | None = None,
    query_description: str | None = None,
    parameters: dict | None = None,
) -> DiscoveryResult:
    if mode_code not in {"automatic", "technology_directed", "name_inference"}:
        raise DiscoveryError("不支持的推演模式")
    selected_ids = sorted(set(selected_technology_ids or []))
    if mode_code == "technology_directed" and not selected_ids:
        raise DiscoveryError("技术词定向推演至少选择一个技术词")
    if mode_code == "name_inference" and not (query_role_name or "").strip():
        raise DiscoveryError("岗位名称推演必须输入岗位名称")

    taxonomy = db.scalar(
        select(TechnologyTaxonomyVersion)
        .where(TechnologyTaxonomyVersion.version_status_code == "active")
        .order_by(
            TechnologyTaxonomyVersion.effective_date.desc(),
            TechnologyTaxonomyVersion.taxonomy_version_id.desc(),
        )
    )
    if taxonomy is None:
        raise DiscoveryError("不存在已激活的技术词体系")
    clustering_run = db.scalar(
        select(JobClusteringRun)
        .where(
            JobClusteringRun.run_status_code == "success",
            JobClusteringRun.target_date <= target_date,
        )
        .order_by(JobClusteringRun.target_date.desc(), JobClusteringRun.clustering_run_id.desc())
    )
    if clustering_run is None:
        raise DiscoveryError("目标日期前不存在成功的岗位聚类运行")
    _validate_selected_technologies(db, taxonomy.taxonomy_version_id, selected_ids)

    config = {**DEFAULT_PARAMETERS, **(parameters or {})}
    snapshot = _build_input_snapshot(
        db,
        taxonomy_version_id=taxonomy.taxonomy_version_id,
        clustering_run=clustering_run,
        target_date=target_date,
        selected_ids=selected_ids,
        query_role_name=query_role_name,
        query_description=query_description,
        parameters=config,
    )
    snapshot_hash = hashlib.sha256(
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    existing = db.scalar(
        select(DiscoveryRun).where(
            DiscoveryRun.mode_code == mode_code,
            DiscoveryRun.algorithm_version == ALGORITHM_VERSION,
            DiscoveryRun.input_snapshot_hash == snapshot_hash,
        )
    )
    if existing and existing.run_status_code == "success":
        summary = existing.result_summary_json or {}
        return DiscoveryResult(
            existing.run_code,
            int(summary.get("candidate_count", 0)),
            int(summary.get("task_count", 0)),
            bool(summary.get("evidence_limited", True)),
            True,
        )

    run = existing or DiscoveryRun(
        run_code=f"discover_{uuid4().hex[:24]}",
        mode_code=mode_code,
        target_date=target_date,
        window_start_date=None,
        clustering_run_id=clustering_run.clustering_run_id,
        taxonomy_version_id=taxonomy.taxonomy_version_id,
        selected_technology_ids_json=selected_ids or None,
        query_role_name=(query_role_name or "").strip() or None,
        query_description=(query_description or "").strip() or None,
        algorithm_version=ALGORITHM_VERSION,
        parameter_json=config,
        input_snapshot_json=snapshot,
        input_snapshot_hash=snapshot_hash,
    )
    run.run_status_code = "running"
    run.started_at = datetime.now(UTC).replace(tzinfo=None)
    db.add(run)
    db.commit()

    try:
        if mode_code == "name_inference":
            candidate_count, task_count = _run_name_inference(db, run)
        else:
            candidate_count, task_count = _run_evidence_discovery(db, run, selected_ids, config)
        verified_milestones = int(snapshot["verified_milestone_count"])
        approved_roles = int(snapshot["approved_role_count"])
        evidence_limited = verified_milestones == 0 or approved_roles == 0
        run.result_summary_json = {
            "candidate_count": candidate_count,
            "task_count": task_count,
            "verified_milestone_count": verified_milestones,
            "approved_role_count": approved_roles,
            "evidence_limited": evidence_limited,
        }
        run.run_status_code = "success"
        run.completed_at = datetime.now(UTC).replace(tzinfo=None)
        db.commit()
        return DiscoveryResult(run.run_code, candidate_count, task_count, evidence_limited)
    except Exception as exc:
        db.rollback()
        failed = db.scalar(select(DiscoveryRun).where(DiscoveryRun.run_code == run.run_code))
        if failed:
            failed.run_status_code = "failed"
            failed.result_summary_json = {"error_type": type(exc).__name__, "message": str(exc)}
            failed.completed_at = datetime.now(UTC).replace(tzinfo=None)
            db.commit()
        raise


def review_candidate(
    db: Session,
    *,
    task_code: str,
    action_code: str,
    actor_user_id: int,
    comment_text: str | None = None,
) -> EmergingRoleCandidate:
    task = db.scalar(select(ReviewTask).where(ReviewTask.task_code == task_code))
    if not task or task.queue_code != "job_discovery" or task.target_type_code != "emerging_role":
        raise DiscoveryError("新岗位专项审批任务不存在")
    candidate = db.get(EmergingRoleCandidate, task.target_id)
    if candidate is None:
        raise DiscoveryError("新岗位候选不存在")
    allowed = {
        "claim": ({"queued"}, "reviewing"),
        "approve": ({"queued", "reviewing", "needs_revision"}, "approved"),
        "reject": ({"queued", "reviewing", "needs_revision"}, "rejected"),
        "needs_revision": ({"queued", "reviewing"}, "needs_revision"),
    }
    if action_code not in allowed:
        raise DiscoveryError("不支持的审批动作")
    from_status = task.task_status_code
    valid_from, to_status = allowed[action_code]
    if from_status not in valid_from:
        raise DiscoveryError(f"任务处于{from_status}，不能执行{action_code}")
    before = candidate_snapshot(db, candidate)
    if action_code == "claim":
        task.assigned_user_id = actor_user_id
        candidate.workflow_status_code = "reviewing"
    elif action_code == "approve":
        _publish_candidate(db, candidate, actor_user_id)
        candidate.workflow_status_code = "approved"
        candidate.maturity_stage_code = "confirmed"
    else:
        candidate.workflow_status_code = to_status
    task.task_status_code = to_status
    db.flush()
    after = candidate_snapshot(db, candidate)
    db.add(
        ReviewAction(
            review_task_id=task.review_task_id,
            actor_user_id=actor_user_id,
            action_code=action_code,
            from_status_code=from_status,
            to_status_code=to_status,
            comment_text=comment_text,
            before_snapshot_json=before,
            after_snapshot_json=after,
        )
    )
    db.commit()
    db.refresh(candidate)
    return candidate


def candidate_snapshot(db: Session, candidate: EmergingRoleCandidate) -> dict:
    technologies = db.execute(
        select(CandidateTechnology, TechnologyNode)
        .join(
            TechnologyNode,
            TechnologyNode.technology_node_id == CandidateTechnology.technology_node_id,
        )
        .where(
            CandidateTechnology.emerging_role_candidate_id == candidate.emerging_role_candidate_id
        )
        .order_by(CandidateTechnology.importance_score.desc())
    ).all()
    score_components = list(
        db.scalars(
            select(CandidateScoreComponent)
            .where(
                CandidateScoreComponent.emerging_role_candidate_id
                == candidate.emerging_role_candidate_id
            )
            .order_by(CandidateScoreComponent.candidate_score_component_id)
        )
    )
    return {
        "candidate_code": candidate.candidate_code,
        "proposed_name": candidate.proposed_name,
        "maturity_stage_code": candidate.maturity_stage_code,
        "workflow_status_code": candidate.workflow_status_code,
        "candidate_score": float(candidate.candidate_score),
        "classification_code": candidate.classification_code,
        "risk_flags": candidate.risk_flags_json,
        "mechanical_card": candidate.mechanical_card_json,
        "expression": candidate.expression_json,
        "expression_model_version": candidate.expression_model_version,
        "approved_role_id": candidate.approved_job_role_id,
        "technologies": [
            {
                "technology_code": node.technology_code,
                "technology_name": node.technology_name,
                "requirement_type": rel.requirement_type_code,
                "importance": float(rel.importance_score),
                "evidence_count": rel.evidence_count,
            }
            for rel, node in technologies
        ],
        "score_components": [
            {
                "component_code": item.component_code,
                "component_type_code": item.component_type_code,
                "raw_score": float(item.raw_score),
                "weight": float(item.weight),
                "weighted_score": float(item.weighted_score),
            }
            for item in score_components
        ],
    }


def apply_candidate_expression(
    db: Session,
    *,
    candidate_code: str,
    proposed_name: str,
    one_line_definition: str,
    core_responsibilities: list[str],
    formation_reason: str,
    difference_explanation: str,
    fact_references: list[str],
    model_version: str,
    generation_method: str = "llm_expression",
) -> EmergingRoleCandidate:
    candidate = db.scalar(
        select(EmergingRoleCandidate).where(EmergingRoleCandidate.candidate_code == candidate_code)
    )
    if candidate is None:
        raise DiscoveryError("新岗位候选不存在")
    if candidate.workflow_status_code not in {"pending", "needs_revision"}:
        raise DiscoveryError("只有待审或待修改候选可以更新表达层")
    card = candidate.mechanical_card_json
    allowed = {
        *(f"task:{item}" for item in card.get("task_ids", [])),
        *(f"technology:{item}" for item in card.get("technology_node_ids", [])),
        *(f"evidence:{item}" for item in card.get("evidence_ids", [])),
    }
    references = set(fact_references)
    if not references or not references.issubset(allowed):
        raise DiscoveryError("LLM表达必须引用机械事实卡中存在的事实ID")
    if not proposed_name.strip() or not one_line_definition.strip() or not core_responsibilities:
        raise DiscoveryError("岗位名称、定义和核心职责不能为空")
    candidate.proposed_name = proposed_name.strip()
    candidate.normalized_name = _normalize_name(proposed_name)
    candidate.expression_json = {
        "name": proposed_name.strip(),
        "one_line_definition": one_line_definition.strip(),
        "core_responsibilities": [item.strip() for item in core_responsibilities if item.strip()],
        "formation_reason": formation_reason.strip(),
        "difference_explanation": difference_explanation.strip(),
        "fact_references": sorted(references),
        "generation_method": generation_method,
    }
    candidate.expression_model_version = model_version
    db.commit()
    db.refresh(candidate)
    return candidate


EXPRESSION_PROMPT_VERSION = "candidate_expression_v1"


def auto_candidate_expression(db: Session, *, candidate_code: str) -> EmergingRoleCandidate:
    """一键生成表达层：LLM 可用时生成并校验，否则规则降级（设计 §8.5、§12.3）。"""
    candidate = db.scalar(
        select(EmergingRoleCandidate).where(
            EmergingRoleCandidate.candidate_code == candidate_code
        )
    )
    if candidate is None:
        raise DiscoveryError("新岗位候选不存在")
    if candidate.workflow_status_code not in {"pending", "needs_revision"}:
        raise DiscoveryError("只有待审或待修改候选可以更新表达层")
    card = candidate.mechanical_card_json or {}
    technologies = candidate_snapshot(db, candidate)["technologies"]
    references = _card_fact_references(card)

    llm_result = _llm_expression(card, candidate, technologies)
    if llm_result is not None:
        return apply_candidate_expression(
            db,
            candidate_code=candidate_code,
            proposed_name=str(llm_result["proposed_name"])[:500],
            one_line_definition=str(llm_result["one_line_definition"])[:3000],
            core_responsibilities=[str(item) for item in llm_result["core_responsibilities"]],
            formation_reason=str(llm_result["formation_reason"])[:5000],
            difference_explanation=str(llm_result["difference_explanation"])[:5000],
            fact_references=references,
            model_version=f"llm:{llm_result['_model']}",
            generation_method="llm_expression",
        )

    fallback = _rule_expression(card, candidate, technologies)
    return apply_candidate_expression(
        db,
        candidate_code=candidate_code,
        proposed_name=candidate.proposed_name,
        one_line_definition=fallback["one_line_definition"],
        core_responsibilities=fallback["core_responsibilities"],
        formation_reason=fallback["formation_reason"],
        difference_explanation=fallback["difference_explanation"],
        fact_references=references,
        model_version="rule_expression_v1",
        generation_method="rule_expression",
    )


def _card_fact_references(card: dict) -> list[str]:
    references = [f"task:{item}" for item in card.get("task_ids", [])]
    references += [f"technology:{item}" for item in card.get("technology_node_ids", [])][:10]
    references += [f"evidence:{item}" for item in card.get("evidence_ids", [])][:10]
    return references or ["task:unknown"]


def _llm_expression(card: dict, candidate, technologies: list[dict]) -> dict | None:
    from app.infrastructure.llm import generate, validate_schema

    facts = {
        "proposed_name": candidate.proposed_name,
        "job_count": card.get("job_count"),
        "organization_count": card.get("organization_count"),
        "task_gap": card.get("task_gap"),
        "maturity_raw": card.get("maturity_raw"),
        "technologies": [
            {"name": item["technology_name"], "requirement_type": item["requirement_type"]}
            for item in technologies[:12]
        ],
    }
    system_prompt = (
        "你是岗位研究助手。只能基于给定机械事实生成岗位表达，"
        "不得新增事实、数字或技能；输出 JSON，包含键：proposed_name、"
        "one_line_definition、core_responsibilities（数组）、formation_reason、"
        "difference_explanation。"
    )
    result = generate(
        system_prompt=system_prompt,
        user_prompt=f"机械事实：{json.dumps(facts, ensure_ascii=False)}",
        prompt_version=EXPRESSION_PROMPT_VERSION,
        json_mode=True,
    )
    if result is None or result.parsed_json is None:
        return None
    data = result.parsed_json
    required = {
        "proposed_name",
        "one_line_definition",
        "core_responsibilities",
        "formation_reason",
        "difference_explanation",
    }
    if not validate_schema(data, required) or not isinstance(
        data.get("core_responsibilities"), list
    ):
        return None
    data["_model"] = result.model
    return data


def _rule_expression(card: dict, candidate, technologies: list[dict]) -> dict:
    required_names = [
        item["technology_name"]
        for item in technologies
        if item["requirement_type"] == "required"
    ][:5]
    bonus_names = [
        item["technology_name"]
        for item in technologies
        if item["requirement_type"] != "required"
    ][:5]
    job_count = int(card.get("job_count", 0))
    org_count = int(card.get("organization_count", 0))
    responsibilities = [
        f"围绕候选任务组合开展工程交付（证据 JD {job_count} 条）",
        f"应用必需技术：{'、'.join(required_names) if required_names else '待补充'}",
    ]
    if bonus_names:
        responsibilities.append(f"加分技术：{'、'.join(bonus_names)}")
    return {
        "one_line_definition": (
            f"基于 {job_count} 条真实 JD、{org_count} 家独立企业的任务缺口证据形成的新岗位候选。"
        ),
        "core_responsibilities": responsibilities,
        "formation_reason": (
            "由技术词、任务缺口与市场支撑的确定性算法计算形成；表达层为规则降级生成，"
            "接入 LLM 后可优化语言。"
        ),
        "difference_explanation": (
            f"与最邻近既有岗位重合度 {card.get('nearest_role_overlap', 0)}，"
            "任务组合未被现有岗位充分覆盖。"
        ),
    }


def _run_evidence_discovery(
    db: Session, run: DiscoveryRun, selected_ids: list[int], parameters: dict
) -> tuple[int, int]:
    maturity = _persist_maturity(db, run, selected_ids)
    pair_evidence = _collect_pair_evidence(db, run, selected_ids)
    ranked = sorted(pair_evidence.items(), key=lambda item: (-len(item[1].job_ids), item[0]))[
        : int(parameters["max_communities"])
    ]
    candidate_count = 0
    task_count = 0
    for technology_ids, evidence in ranked:
        if len(evidence.job_ids) < int(parameters["min_pair_job_count"]):
            continue
        task = _persist_task(db, run, technology_ids, evidence, maturity)
        task_count += 1
        community = TaskCommunity(
            discovery_run_id=run.discovery_run_id,
            community_code=f"community_{_stable_digest(technology_ids)[:16]}",
            community_label=task.task_name,
            grouping_method_code="technology_cooccurrence_fallback",
            cohesion_score=Decimal("1.000000" if len(technology_ids) == 1 else "0.750000"),
            task_count=1,
            community_snapshot_json={
                "technology_node_ids": list(technology_ids),
                "fallback_reason": "task_graph_density_insufficient",
            },
        )
        db.add(community)
        db.flush()
        db.add(
            TaskCommunityMember(
                task_community_id=community.task_community_id,
                industry_task_id=task.industry_task_id,
                member_role_code="core",
                membership_score=Decimal("1"),
            )
        )
        _persist_candidate(db, run, community, task, technology_ids, evidence, maturity)
        candidate_count += 1
    return candidate_count, task_count


def _collect_pair_evidence(
    db: Session, run: DiscoveryRun, selected_ids: list[int]
) -> dict[tuple[int, ...], _PairEvidence]:
    cutoff = datetime.combine(run.target_date, datetime.max.time())
    accepted = db.execute(
        select(JobRequirement, JobPosting, TechnologyMatchAssessment.evidence_span_id)
        .join(JobPosting, JobPosting.job_posting_id == JobRequirement.job_posting_id)
        .join(
            TechnologyMatchAssessment,
            TechnologyMatchAssessment.job_requirement_id == JobRequirement.job_requirement_id,
        )
        .where(
            JobRequirement.technology_node_id.is_not(None),
            TechnologyMatchAssessment.assessment_status_code == "accepted",
            or_(
                JobPosting.source_collected_at <= cutoff,
                (JobPosting.source_collected_at.is_(None)) & (JobPosting.published_at <= cutoff),
            ),
        )
    ).all()
    jobs: dict[int, tuple[JobPosting, set[int], set[int]]] = {}
    for requirement, posting, evidence_id in accepted:
        if posting.job_posting_id not in jobs:
            jobs[posting.job_posting_id] = (posting, set(), set())
        jobs[posting.job_posting_id][1].add(requirement.technology_node_id)
        jobs[posting.job_posting_id][2].add(evidence_id)
    responsibilities = defaultdict(list)
    for responsibility in db.scalars(
        select(JobResponsibility).where(JobResponsibility.job_posting_id.in_(list(jobs) or [-1]))
    ):
        responsibilities[responsibility.job_posting_id].append(responsibility)
    sources = defaultdict(set)
    for job_id, source_id in db.execute(
        select(JobPostingDataSource.job_posting_id, JobPostingDataSource.data_source_id).where(
            JobPostingDataSource.job_posting_id.in_(list(jobs) or [-1])
        )
    ):
        sources[job_id].add(source_id)
    result = {}
    selected = set(selected_ids)
    for job_id, (posting, technology_ids, evidence_ids) in jobs.items():
        if selected and not selected.issubset(technology_ids):
            continue
        if selected:
            keys = [tuple(selected_ids)]
        elif len(technology_ids) == 1:
            keys = [tuple(sorted(technology_ids))]
        else:
            keys = list(combinations(sorted(technology_ids), 2))
        for key in keys:
            bucket = result.setdefault(key, _PairEvidence(set(), set(), set(), set(), [], {}))
            bucket.job_ids.add(job_id)
            if posting.organization_id:
                bucket.organization_ids.add(posting.organization_id)
            bucket.source_ids.update(sources[job_id] or {posting.data_source_id})
            if posting.source_collected_at:
                bucket.observation_windows.add(posting.source_collected_at.strftime("%Y-%m"))
            bucket.responsibilities.extend(responsibilities[job_id])
            bucket.evidence_job_ids.update({evidence_id: job_id for evidence_id in evidence_ids})
    return result


def _persist_maturity(db: Session, run: DiscoveryRun, selected_ids: list[int]) -> dict[int, float]:
    technology_ids = selected_ids or list(
        db.scalars(
            select(TechnologyNode.technology_node_id).where(
                TechnologyNode.taxonomy_version_id == run.taxonomy_version_id,
                TechnologyNode.governance_status_code == "active",
            )
        )
    )
    result = {}
    for technology_id in technology_ids:
        event_rows = db.execute(
            select(
                MilestoneEvent, MilestoneTechnology, func.avg(EvidenceSpan.source_reliability_score)
            )
            .join(
                MilestoneTechnology,
                MilestoneTechnology.milestone_event_id == MilestoneEvent.milestone_event_id,
            )
            .outerjoin(
                MilestoneEvidence,
                MilestoneEvidence.milestone_event_id == MilestoneEvent.milestone_event_id,
            )
            .outerjoin(
                EvidenceSpan, EvidenceSpan.evidence_span_id == MilestoneEvidence.evidence_span_id
            )
            .where(
                MilestoneTechnology.technology_node_id == technology_id,
                MilestoneEvent.verification_status_code == "verified",
                MilestoneEvent.event_date.is_not(None),
                MilestoneEvent.event_date <= run.target_date,
            )
            .group_by(
                MilestoneEvent.milestone_event_id,
                MilestoneTechnology.milestone_event_id,
                MilestoneTechnology.technology_node_id,
            )
        ).all()
        signals = [
            MaturityEventSignal(
                event_id=event.milestone_event_id,
                event_type_code=event.milestone_type_code,
                age_years=max(0, (run.target_date - event.event_date).days / 365.25),
                relevance=float(relation.relevance_score) / 100,
                source_quality=float(source_quality or 60) / 100,
            )
            for event, relation, source_quality in event_rows
        ]
        maturity = calculate_maturity(signals)
        snapshot = TechnologyMaturitySnapshot(
            discovery_run_id=run.discovery_run_id,
            technology_node_id=technology_id,
            maturity_raw_score=Decimal(str(maturity.raw)),
            maturity_explore_score=Decimal(str(maturity.explore)),
            verified_event_count=len(signals),
            evidence_status_code="verified" if signals else "missing_verified_milestone",
        )
        db.add(snapshot)
        db.flush()
        for contribution in maturity.contributions:
            db.add(
                MaturityEventContribution(
                    maturity_snapshot_id=snapshot.maturity_snapshot_id,
                    milestone_event_id=contribution.event_id,
                    type_weight=Decimal(str(contribution.type_weight)),
                    relevance_score=Decimal(str(contribution.relevance)),
                    recency_score=Decimal(str(contribution.recency)),
                    source_quality_score=Decimal(str(contribution.source_quality)),
                    contribution_score=Decimal(str(contribution.contribution)),
                )
            )
        result[technology_id] = maturity.raw
    return result


def _persist_task(
    db: Session,
    run: DiscoveryRun,
    technology_ids: tuple[int, ...],
    evidence: _PairEvidence,
    maturity: dict[int, float],
) -> IndustryTask:
    responsibility = _representative_responsibility(evidence.responsibilities)
    market = calculate_market_support(
        job_count=len(evidence.job_ids),
        organization_count=len(evidence.organization_ids),
        source_count=len(evidence.source_ids),
        observation_window_count=len(evidence.observation_windows),
        application_evidence_count=_application_evidence_count(db, run, technology_ids),
    )
    coverage = _existing_role_coverage(db, technology_ids, run.target_date)
    evidence_strength = min(1.0, 0.35 + 0.08 * len(evidence.evidence_job_ids))
    maturity_score = sum(maturity.get(item, 0) for item in technology_ids) / len(technology_ids)
    gap = calculate_task_gap(
        technology_relevance=1.0,
        maturity=max(0.15, maturity_score),
        existing_role_coverage=coverage,
        evidence_strength=evidence_strength,
        organization_count=len(evidence.organization_ids),
        market_support=market,
    )
    text = responsibility.normalized_task_text if responsibility else None
    task = IndustryTask(
        discovery_run_id=run.discovery_run_id,
        task_code=f"task_{_stable_digest(technology_ids)[:20]}",
        task_name=text or " / ".join(str(item) for item in technology_ids),
        normalized_task_text=text or "技术组合工程任务",
        action_verb=responsibility.action_verb if responsibility else None,
        task_object=responsibility.task_object if responsibility else None,
        expected_output=responsibility.expected_output if responsibility else None,
        evidence_strength_score=Decimal(str(evidence_strength)),
        market_support_score=Decimal(str(market)),
        existing_role_coverage_score=Decimal(str(coverage)),
        task_gap_score=Decimal(str(gap)),
        job_count=len(evidence.job_ids),
        organization_count=len(evidence.organization_ids),
        source_count=len(evidence.source_ids),
        evidence_status_code=("traceable" if evidence.evidence_job_ids else "missing_span"),
    )
    db.add(task)
    db.flush()
    for technology_id in technology_ids:
        db.add(
            IndustryTaskTechnology(
                industry_task_id=task.industry_task_id,
                technology_node_id=technology_id,
                relation_type_code="depends_on",
                relevance_score=Decimal("1"),
            )
        )
    for evidence_id, job_id in sorted(evidence.evidence_job_ids.items()):
        db.add(
            IndustryTaskEvidence(
                industry_task_id=task.industry_task_id,
                evidence_span_id=evidence_id,
                job_posting_id=job_id,
                evidence_type_code="accepted_technology_context",
                support_score=Decimal("1"),
            )
        )
    return task


def _persist_candidate(
    db: Session,
    run: DiscoveryRun,
    community: TaskCommunity,
    task: IndustryTask,
    technology_ids: tuple[int, ...],
    evidence: _PairEvidence,
    maturity: dict[int, float],
) -> EmergingRoleCandidate:
    technologies = list(
        db.scalars(
            select(TechnologyNode)
            .where(TechnologyNode.technology_node_id.in_(technology_ids))
            .order_by(TechnologyNode.level_code.desc(), TechnologyNode.technology_code)
        )
    )
    names = [item.technology_name for item in technologies]
    proposed_name = "与".join(names[:2]) + "工程师"
    application_count = _application_evidence_count(db, run, technology_ids)
    raw_maturity = sum(maturity.get(item, 0) for item in technology_ids) / len(technology_ids)
    signals = CandidateSignals(
        technology_relevance=1.0,
        publication_task_gap=float(task.task_gap_score),
        community_cohesion=float(community.cohesion_score),
        market_support=float(task.market_support_score),
        technology_maturity=raw_maturity,
        temporal_growth_stability=min(1.0, len(evidence.observation_windows) / 3),
        evidence_completeness=min(1.0, len(evidence.evidence_job_ids) / 5),
        novelty=1 - float(task.existing_role_coverage_score),
        job_count=len(evidence.job_ids),
        organization_count=len(evidence.organization_ids),
        source_count=len(evidence.source_ids),
        observation_window_count=len(evidence.observation_windows),
        application_evidence_count=application_count,
    )
    scored = score_candidate(signals)
    nearest_role_id, overlap = _nearest_role(db, technology_ids, run.target_date)
    classification = (
        "existing_role"
        if overlap >= 0.75
        else "role_evolution"
        if overlap >= 0.45
        else "potential_new_role"
    )
    mechanical = {
        "fact_schema_version": "mechanical_role_card_v1",
        "technology_node_ids": list(technology_ids),
        "technology_names": names,
        "task_ids": [task.industry_task_id],
        "job_count": len(evidence.job_ids),
        "organization_count": len(evidence.organization_ids),
        "source_count": len(evidence.source_ids),
        "observation_window_count": len(evidence.observation_windows),
        "verified_application_evidence_count": application_count,
        "maturity_raw": raw_maturity,
        "task_gap": float(task.task_gap_score),
        "nearest_role_overlap": overlap,
        "evidence_ids": sorted(evidence.evidence_job_ids),
        "llm_boundary": "expression_only_no_fact_mutation",
    }
    candidate = EmergingRoleCandidate(
        discovery_run_id=run.discovery_run_id,
        task_community_id=community.task_community_id,
        candidate_code=f"candidate_{uuid4().hex[:20]}",
        proposed_name=proposed_name,
        normalized_name=_normalize_name(proposed_name),
        maturity_stage_code=scored.maturity_stage,
        workflow_status_code="pending",
        candidate_score=Decimal(str(scored.score)),
        nearest_job_role_id=nearest_role_id,
        overlap_score=Decimal(str(overlap)),
        classification_code=classification,
        mechanical_card_json=mechanical,
        expression_json={
            "name": proposed_name,
            "one_line_definition": f"负责{task.task_name}并交付可验证工程成果的岗位。",
            "core_responsibilities": [task.normalized_task_text],
            "generation_method": "mechanical_fallback",
            "fact_references": [f"task:{task.industry_task_id}"],
        },
        expression_model_version=None,
        risk_flags_json=list(scored.risk_flags),
    )
    db.add(candidate)
    db.flush()
    for component in scored.components:
        db.add(
            CandidateScoreComponent(
                emerging_role_candidate_id=candidate.emerging_role_candidate_id,
                component_code=component.code,
                component_type_code=component.component_type,
                raw_score=Decimal(str(component.raw_score)),
                weight=Decimal(str(component.weight)),
                weighted_score=Decimal(str(component.weighted_score)),
                explanation_json=None,
            )
        )
    per_tech_evidence = max(1, len(evidence.evidence_job_ids) // len(technology_ids))
    for technology_id in technology_ids:
        db.add(
            CandidateTechnology(
                emerging_role_candidate_id=candidate.emerging_role_candidate_id,
                technology_node_id=technology_id,
                requirement_type_code="required",
                importance_score=Decimal("1"),
                evidence_count=per_tech_evidence,
            )
        )
    db.add(
        ReviewTask(
            task_code=f"review_discovery_{candidate.candidate_code}",
            queue_code="job_discovery",
            target_type_code="emerging_role",
            target_id=candidate.emerging_role_candidate_id,
            priority_score=candidate.candidate_score,
            task_status_code="queued",
            target_snapshot_json=candidate_snapshot(db, candidate),
            reason_json={"risk_flags": list(scored.risk_flags)},
        )
    )
    return candidate


def _run_name_inference(db: Session, run: DiscoveryRun) -> tuple[int, int]:
    query = _normalize_name(run.query_role_name or "")
    role = db.scalar(
        select(JobRole)
        .outerjoin(JobRoleAlias, JobRoleAlias.job_role_id == JobRole.job_role_id)
        .where(
            JobRole.lifecycle_status_code == "active",
            or_(JobRole.normalized_name == query, JobRoleAlias.normalized_alias == query),
        )
    )
    historical_candidate = db.scalar(
        select(EmergingRoleCandidate)
        .where(EmergingRoleCandidate.normalized_name == query)
        .order_by(EmergingRoleCandidate.created_at.desc())
    )
    jd_count = (
        db.scalar(
            select(func.count(JobPosting.job_posting_id)).where(
                JobPosting.job_title_normalized == run.query_role_name,
                or_(
                    JobPosting.source_collected_at
                    <= datetime.combine(run.target_date, datetime.max.time()),
                    JobPosting.published_at
                    <= datetime.combine(run.target_date, datetime.max.time()),
                ),
            )
        )
        or 0
    )
    classification = (
        "existing_role"
        if role
        else "existing_candidate"
        if historical_candidate
        else "insufficient_evidence"
    )
    proposed_name = role.canonical_name if role else run.query_role_name or "未命名岗位"
    candidate = EmergingRoleCandidate(
        discovery_run_id=run.discovery_run_id,
        task_community_id=None,
        candidate_code=f"candidate_{uuid4().hex[:20]}",
        proposed_name=proposed_name,
        normalized_name=query,
        maturity_stage_code="confirmed" if role else "potential",
        workflow_status_code="merged" if role or historical_candidate else "pending",
        candidate_score=Decimal("100" if role else "40" if historical_candidate else "10"),
        nearest_job_role_id=role.job_role_id if role else None,
        overlap_score=Decimal("1" if role else "0"),
        classification_code=classification,
        mechanical_card_json={
            "query_role_name": run.query_role_name,
            "query_description": run.query_description,
            "formal_role_match": role.role_code if role else None,
            "historical_candidate_match": historical_candidate.candidate_code
            if historical_candidate
            else None,
            "exact_jd_title_count": jd_count,
            "conclusion": classification,
        },
        expression_json=None,
        risk_flags_json=[] if role else ["name_query_is_not_market_proof"],
    )
    db.add(candidate)
    db.flush()
    if candidate.workflow_status_code == "pending":
        db.add(
            ReviewTask(
                task_code=f"review_discovery_{candidate.candidate_code}",
                queue_code="job_discovery",
                target_type_code="emerging_role",
                target_id=candidate.emerging_role_candidate_id,
                priority_score=candidate.candidate_score,
                task_status_code="queued",
                target_snapshot_json=candidate_snapshot(db, candidate),
                reason_json={"risk_flags": candidate.risk_flags_json},
            )
        )
    return 1, 0


def _publish_candidate(db: Session, candidate: EmergingRoleCandidate, actor_user_id: int) -> None:
    if candidate.classification_code in {"existing_role", "existing_candidate"}:
        raise DiscoveryError("已有岗位或已有候选不能作为新岗位重复发布")
    if candidate.approved_job_role_id:
        raise DiscoveryError("候选已经发布")
    technology_count = db.scalar(
        select(func.count())
        .select_from(CandidateTechnology)
        .where(
            CandidateTechnology.emerging_role_candidate_id == candidate.emerging_role_candidate_id
        )
    )
    if (
        not candidate.task_community_id
        or not technology_count
        or not candidate.mechanical_card_json.get("evidence_ids")
    ):
        raise DiscoveryError("候选缺少可追溯任务、技术词或证据片段，不能发布正式岗位")
    expression = candidate.expression_json or {}
    normalized = _normalize_name(candidate.proposed_name)
    if db.scalar(select(JobRole).where(JobRole.normalized_name == normalized)):
        raise DiscoveryError("正式岗位库已存在同名岗位")
    role = JobRole(
        role_code=f"ROLE-N-{uuid4().hex[:12].upper()}",
        canonical_name=candidate.proposed_name,
        normalized_name=normalized,
        origin_type_code="inference_derived",
        lifecycle_status_code="active",
        first_detected_at=candidate.created_at,
        approved_at=datetime.now(UTC).replace(tzinfo=None),
    )
    db.add(role)
    db.flush()
    version = JobRoleVersion(
        job_role_id=role.job_role_id,
        version_no=1,
        previous_version_id=None,
        valid_from=date.today(),
        valid_to=None,
        role_name=candidate.proposed_name,
        one_line_definition=expression.get("one_line_definition") or "经专项审批发布的新岗位。",
        core_responsibility_text="\n".join(expression.get("core_responsibilities") or []),
        job_level_distribution_json=None,
        update_summary="新岗位发现专项审批创建首版本",
        generation_method_code="discovery_mechanical_llm",
        evidence_strength_score=candidate.candidate_score,
        approval_status_code="approved",
        approved_by_user_id=actor_user_id,
        approved_at=datetime.now(UTC).replace(tzinfo=None),
    )
    db.add(version)
    db.flush()
    for rel in db.scalars(
        select(CandidateTechnology).where(
            CandidateTechnology.emerging_role_candidate_id == candidate.emerging_role_candidate_id
        )
    ):
        db.add(
            JobRoleVersionRequirement(
                job_role_version_id=version.job_role_version_id,
                technology_node_id=rel.technology_node_id,
                requirement_type_code=rel.requirement_type_code,
                required_level_code=None,
                long_term_importance_score=rel.importance_score * 100,
                recent_activity_score=rel.importance_score * 100,
                coverage_rate=None,
                required_ratio=None,
                trend_score=None,
                trend_status_code="initial_definition",
                supporting_job_count=int(candidate.mechanical_card_json.get("job_count", 0)),
                independent_organization_count=int(
                    candidate.mechanical_card_json.get("organization_count", 0)
                ),
                independent_source_count=int(candidate.mechanical_card_json.get("source_count", 0)),
                last_seen_at=None,
                confidence_score=candidate.candidate_score,
                is_human_edited=False,
            )
        )
    standard_content = {
        "title": candidate.proposed_name,
        "definition": version.one_line_definition,
        "responsibilities": expression.get("core_responsibilities") or [],
        "technology_node_ids": candidate.mechanical_card_json.get("technology_node_ids", []),
        "disclaimer": "参考模板，不代表真实招聘，不计入市场热度与岗位证据。",
    }
    db.add(
        StandardJobDescription(
            standard_jd_code=f"SJD-{uuid4().hex[:16].upper()}",
            emerging_role_candidate_id=candidate.emerging_role_candidate_id,
            job_role_version_id=version.job_role_version_id,
            version_no=1,
            title_text=candidate.proposed_name,
            content_json=standard_content,
            generation_method_code="mechanical",
            model_version=None,
            is_market_evidence=False,
            approval_status_code="approved",
        )
    )
    candidate.approved_job_role_id = role.job_role_id


def _build_input_snapshot(
    db: Session,
    *,
    taxonomy_version_id: int,
    clustering_run: JobClusteringRun,
    target_date: date,
    selected_ids: list[int],
    query_role_name: str | None,
    query_description: str | None,
    parameters: dict,
) -> dict:
    verified_ids = list(
        db.scalars(
            select(MilestoneEvent.milestone_event_id)
            .where(
                MilestoneEvent.verification_status_code == "verified",
                MilestoneEvent.event_date.is_not(None),
                MilestoneEvent.event_date <= target_date,
            )
            .order_by(MilestoneEvent.milestone_event_id)
        )
    )
    approved_version_ids = list(
        db.scalars(
            select(JobRoleVersion.job_role_version_id)
            .join(JobRole, JobRole.job_role_id == JobRoleVersion.job_role_id)
            .where(
                JobRole.lifecycle_status_code == "active",
                JobRoleVersion.approval_status_code == "approved",
                JobRoleVersion.valid_from <= target_date,
                or_(JobRoleVersion.valid_to.is_(None), JobRoleVersion.valid_to >= target_date),
            )
            .order_by(JobRoleVersion.job_role_version_id)
        )
    )
    cutoff = datetime.combine(target_date, datetime.max.time())
    accepted_assessment_ids = list(
        db.scalars(
            select(TechnologyMatchAssessment.technology_match_assessment_id)
            .join(
                JobRequirement,
                JobRequirement.job_requirement_id == TechnologyMatchAssessment.job_requirement_id,
            )
            .join(JobPosting, JobPosting.job_posting_id == JobRequirement.job_posting_id)
            .where(
                TechnologyMatchAssessment.assessment_status_code == "accepted",
                or_(
                    JobPosting.source_collected_at <= cutoff,
                    (JobPosting.source_collected_at.is_(None))
                    & (JobPosting.published_at <= cutoff),
                ),
            )
            .order_by(TechnologyMatchAssessment.technology_match_assessment_id)
        )
    )
    return {
        "target_date": target_date.isoformat(),
        "taxonomy_version_id": taxonomy_version_id,
        "clustering_run_id": clustering_run.clustering_run_id,
        "clustering_input_hash": clustering_run.input_snapshot_hash,
        "selected_technology_ids": selected_ids,
        "query_role_name": (query_role_name or "").strip() or None,
        "query_description": (query_description or "").strip() or None,
        "verified_milestone_ids": verified_ids,
        "verified_milestone_count": len(verified_ids),
        "approved_role_version_ids": approved_version_ids,
        "approved_role_count": len(approved_version_ids),
        "accepted_technology_assessment_ids": accepted_assessment_ids,
        "accepted_technology_assessment_count": len(accepted_assessment_ids),
        "parameters": parameters,
    }


def _validate_selected_technologies(db: Session, taxonomy_version_id: int, ids: list[int]) -> None:
    if not ids:
        return
    valid = set(
        db.scalars(
            select(TechnologyNode.technology_node_id).where(
                TechnologyNode.technology_node_id.in_(ids),
                TechnologyNode.taxonomy_version_id == taxonomy_version_id,
                TechnologyNode.governance_status_code == "active",
            )
        )
    )
    if valid != set(ids):
        raise DiscoveryError("选择的技术词不存在、未激活或不属于当前技术体系")


def _application_evidence_count(db: Session, run: DiscoveryRun, ids: tuple[int, ...]) -> int:
    return int(
        db.scalar(
            select(func.count(func.distinct(MilestoneEvent.milestone_event_id)))
            .join(MilestoneTechnology)
            .where(
                MilestoneTechnology.technology_node_id.in_(ids),
                MilestoneEvent.verification_status_code == "verified",
                MilestoneEvent.event_date.is_not(None),
                MilestoneEvent.event_date <= run.target_date,
                MilestoneEvent.milestone_type_code.in_(
                    ["enterprise_application", "scaled_deployment", "product_release"]
                ),
            )
        )
        or 0
    )


def _nearest_role(
    db: Session, technology_ids: tuple[int, ...], target_date: date
) -> tuple[int | None, float]:
    versions = list(
        db.scalars(
            select(JobRoleVersion).where(
                JobRoleVersion.approval_status_code == "approved",
                JobRoleVersion.valid_from <= target_date,
                or_(JobRoleVersion.valid_to.is_(None), JobRoleVersion.valid_to >= target_date),
            )
        )
    )
    best_role_id = None
    best_overlap = 0.0
    target = set(technology_ids)
    for version in versions:
        role_tech = set(
            db.scalars(
                select(JobRoleVersionRequirement.technology_node_id).where(
                    JobRoleVersionRequirement.job_role_version_id == version.job_role_version_id
                )
            )
        )
        overlap = len(target & role_tech) / len(target | role_tech) if target | role_tech else 0.0
        if overlap > best_overlap:
            best_role_id = version.job_role_id
            best_overlap = overlap
    return best_role_id, best_overlap


def _existing_role_coverage(db: Session, ids: tuple[int, ...], target_date: date) -> float:
    return _nearest_role(db, ids, target_date)[1]


def _representative_responsibility(rows: list[JobResponsibility]) -> JobResponsibility | None:
    if not rows:
        return None
    counts = Counter((item.normalized_task_text or item.raw_text).strip() for item in rows)
    text = sorted(counts, key=lambda item: (-counts[item], item))[0]
    return next(
        item for item in rows if (item.normalized_task_text or item.raw_text).strip() == text
    )


def _stable_digest(values: tuple[int, ...]) -> str:
    return hashlib.sha256("|".join(map(str, values)).encode()).hexdigest()


def _normalize_name(value: str) -> str:
    return re.sub(r"[\s\-_—/（）()]+", "", value.strip().lower())
