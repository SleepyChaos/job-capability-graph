import hashlib
import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.clustering.models import JobClusterMember, JobClusterVersion
from app.modules.graph.service import (
    _active_clusters,
    _cluster_capability_metrics,
    _cluster_memberships,
    _context,
    _signals_by_job,
)
from app.modules.job.models import JobPosting
from app.modules.talent.models import (
    CandidateDialogueTurn,
    CandidateLearningPath,
    CandidateMatchGap,
    CandidateMatchResult,
    CandidateMatchRun,
    CandidateProfile,
    CandidateProfileVersion,
    CandidateSkillEvidence,
    ResumeDocument,
)
from app.modules.taxonomy.models import TechnologyAlias, TechnologyNode

PROFILE_PARSER_VERSION = "candidate_profile_rules_v1"
MATCH_ALGORITHM_VERSION = "evidence_match_p0_v1"
PATH_ALGORITHM_VERSION = "gap_path_rules_p0_v1"
MIN_DIALOGUE_ROUNDS = 2
MAX_DIALOGUE_ROUNDS = 8


class TalentWorkflowError(ValueError):
    """A user-correctable talent workflow error."""


QUESTION_BANK = (
    (
        "target_role",
        "你目前最想进入哪类具身智能岗位？也可以描述更喜欢的工作内容。",
    ),
    (
        "representative_project",
        "哪段项目最能代表你的能力？请说明你负责的任务和可验证结果。",
    ),
    (
        "work_preference",
        "你更偏向研究探索、工程交付、现场部署，还是跨模块协调？",
    ),
    ("target_level", "你的目标岗位级别和可接受的转型跨度是什么？"),
    ("target_scenario", "你更希望进入哪些具身智能应用场景或机器人形态？"),
    ("development_horizon", "你希望在多长时间内完成这次能力转型？"),
    ("constraints", "有哪些明确不考虑的方向、地点或工作条件？"),
    ("additional_evidence", "还有哪些项目、论文、竞赛或开源成果值得作为能力证据？"),
)


def create_profile_draft(
    db: Session,
    *,
    source_name: str,
    mime_type: str,
    content_text: str,
    input_type_code: str = "pasted_text",
) -> dict:
    text = _clean_untrusted_text(content_text)
    if len(text) < 30:
        raise TalentWorkflowError("简历文本至少需要30个有效字符")
    if len(text) > 200_000:
        raise TalentWorkflowError("P0单份简历文本不能超过20万字符")
    document = ResumeDocument(
        document_code=f"RES-{uuid4().hex[:20]}",
        source_name=source_name.strip() or "粘贴文本简历",
        mime_type=mime_type,
        input_type_code=input_type_code,
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        content_text=text,
        parser_version=PROFILE_PARSER_VERSION,
    )
    db.add(document)
    db.flush()
    facts = _extract_basic_facts(text)
    profile = CandidateProfile(
        profile_code=f"CP-{uuid4().hex[:18]}",
        display_name=facts["display_name"],
    )
    db.add(profile)
    db.flush()
    version = CandidateProfileVersion(
        candidate_profile_id=profile.candidate_profile_id,
        resume_document_id=document.resume_document_id,
        version_code=f"CPV-{uuid4().hex[:18]}",
        version_no=1,
        workflow_status_code="draft",
        target_role_text=facts.get("target_role"),
        education_text=facts.get("education"),
        experience_summary=facts.get("experience_summary"),
        preference_json={},
        fact_json={
            "source_labels": {
                "display_name": "resume_fact",
                "target_role": "resume_fact" if facts.get("target_role") else "insufficient",
                "education": "resume_fact" if facts.get("education") else "insufficient",
            },
            "raw_section_count": len([line for line in text.splitlines() if line.strip()]),
        },
        insight_json={
            "status": "draft_hypothesis",
            "statements": [],
            "warning": "洞察只基于可见证据和用户补充，不进行人格判定。",
        },
        completeness_score=Decimal("0"),
        parser_version=PROFILE_PARSER_VERSION,
    )
    db.add(version)
    db.flush()
    _extract_skill_evidence(db, version, text)
    question = _ensure_next_question(db, version)
    _update_completeness(db, version)
    db.commit()
    return profile_snapshot(db, version, next_question=question)


def answer_profile_question(db: Session, *, version_code: str, answer_text: str) -> dict:
    version = _get_version(db, version_code)
    if version.workflow_status_code != "draft":
        raise TalentWorkflowError("只有草稿画像可以继续回答问题")
    turn = db.scalar(
        select(CandidateDialogueTurn)
        .where(
            CandidateDialogueTurn.candidate_profile_version_id
            == version.candidate_profile_version_id,
            CandidateDialogueTurn.answer_text.is_(None),
        )
        .order_by(CandidateDialogueTurn.turn_no)
    )
    if turn is None:
        raise TalentWorkflowError("当前没有待回答问题")
    answer = answer_text.strip()
    if not answer:
        raise TalentWorkflowError("回答不能为空")
    turn.answer_text = answer
    version.conversation_round_count += 1
    preferences = dict(version.preference_json or {})
    preferences[turn.question_code] = {
        "value": answer,
        "source": "user_confirmed",
        "turn_no": turn.turn_no,
    }
    version.preference_json = preferences
    if turn.question_code == "target_role" and not version.target_role_text:
        version.target_role_text = answer[:500]
    next_question = None
    if not _dialogue_can_finish(version):
        next_question = _ensure_next_question(db, version)
    _update_completeness(db, version)
    db.commit()
    return profile_snapshot(db, version, next_question=next_question)


def publish_profile(db: Session, *, version_code: str) -> dict:
    version = _get_version(db, version_code)
    if version.workflow_status_code == "confirmed":
        return profile_snapshot(db, version)
    if version.conversation_round_count < MIN_DIALOGUE_ROUNDS:
        raise TalentWorkflowError("至少完成2轮补充问答后才能确认画像")
    skills = _skills(db, version.candidate_profile_version_id)
    preferences = version.preference_json or {}
    version.insight_json = {
        "status": "user_confirmed_profile",
        "statements": [
            {
                "text": (
                    f"已有{len(skills)}项标准技术能力证据，适合从证据最充分的能力组合开始匹配。"
                ),
                "source": "system_inference",
                "evidence_ids": [
                    f"skill:{item.candidate_skill_evidence_id}" for item in skills[:8]
                ],
            },
            {
                "text": str(preferences.get("work_preference", {}).get("value", "工作方式待补充")),
                "source": "user_confirmed" if "work_preference" in preferences else "insufficient",
                "evidence_ids": [],
            },
        ],
        "warning": "洞察不进入敏感属性判断，缺少简历证据不等于候选人不会。",
    }
    version.workflow_status_code = "confirmed"
    version.published_at = datetime.now()
    _update_completeness(db, version)
    db.commit()
    return profile_snapshot(db, version)


def create_profile_version(
    db: Session,
    *,
    version_code: str,
    target_role_text: str | None = None,
    education_text: str | None = None,
    experience_summary: str | None = None,
) -> dict:
    previous = _get_version(db, version_code)
    max_version = (
        db.scalar(
            select(func.max(CandidateProfileVersion.version_no)).where(
                CandidateProfileVersion.candidate_profile_id == previous.candidate_profile_id
            )
        )
        or 0
    )
    version = CandidateProfileVersion(
        candidate_profile_id=previous.candidate_profile_id,
        resume_document_id=previous.resume_document_id,
        version_code=f"CPV-{uuid4().hex[:18]}",
        version_no=max_version + 1,
        previous_version_id=previous.candidate_profile_version_id,
        workflow_status_code="draft",
        target_role_text=target_role_text or previous.target_role_text,
        education_text=education_text or previous.education_text,
        experience_summary=experience_summary or previous.experience_summary,
        preference_json=dict(previous.preference_json or {}),
        fact_json=dict(previous.fact_json or {}),
        insight_json={"status": "needs_reconfirmation", "statements": []},
        completeness_score=previous.completeness_score,
        conversation_round_count=previous.conversation_round_count,
        parser_version=previous.parser_version,
    )
    db.add(version)
    db.flush()
    for skill in _skills(db, previous.candidate_profile_version_id):
        db.add(
            CandidateSkillEvidence(
                candidate_profile_version_id=version.candidate_profile_version_id,
                technology_node_id=skill.technology_node_id,
                raw_mention=skill.raw_mention,
                evidence_text=skill.evidence_text,
                source_type_code=skill.source_type_code,
                evidence_level_code=skill.evidence_level_code,
                proficiency_score=skill.proficiency_score,
                confidence_score=skill.confidence_score,
                user_confirmed=skill.user_confirmed,
            )
        )
    db.commit()
    return profile_snapshot(db, version)


def list_profiles(db: Session) -> list[dict]:
    rows = db.execute(
        select(CandidateProfileVersion, CandidateProfile, ResumeDocument)
        .join(
            CandidateProfile,
            CandidateProfile.candidate_profile_id == CandidateProfileVersion.candidate_profile_id,
        )
        .join(
            ResumeDocument,
            ResumeDocument.resume_document_id == CandidateProfileVersion.resume_document_id,
        )
        .order_by(CandidateProfileVersion.created_at.desc())
    ).all()
    return [_profile_summary(db, version, profile, document) for version, profile, document in rows]


def get_profile(db: Session, *, version_code: str) -> dict:
    return profile_snapshot(db, _get_version(db, version_code))


def run_matching(db: Session, *, version_code: str, limit: int = 5) -> dict:
    version = _get_version(db, version_code)
    if version.workflow_status_code != "confirmed":
        raise TalentWorkflowError("只有已确认画像可以发起岗位匹配")
    context = _context(db)
    profile_skills = _skills(db, version.candidate_profile_version_id)
    profile_skill_ids = {item.technology_node_id for item in profile_skills}
    profile_l2 = {
        _ancestor_at_level(context.nodes, technology_id, "L2")
        for technology_id in profile_skill_ids
    }
    profile_l2.discard(None)
    snapshot_payload = {
        "version_code": version.version_code,
        "skill_ids": sorted(profile_skill_ids),
        "target_role": version.target_role_text,
        "clustering_run": context.run.run_code,
    }
    snapshot_hash = hashlib.sha256(repr(snapshot_payload).encode("utf-8")).hexdigest()
    existing = db.scalar(
        select(CandidateMatchRun).where(
            CandidateMatchRun.candidate_profile_version_id == version.candidate_profile_version_id,
            CandidateMatchRun.clustering_run_id == context.run.clustering_run_id,
            CandidateMatchRun.algorithm_version == MATCH_ALGORITHM_VERSION,
            CandidateMatchRun.input_snapshot_hash == snapshot_hash,
        )
    )
    if existing:
        return match_run_snapshot(db, existing)
    run = CandidateMatchRun(
        run_code=f"CMR-{uuid4().hex[:18]}",
        candidate_profile_version_id=version.candidate_profile_version_id,
        clustering_run_id=context.run.clustering_run_id,
        algorithm_version=MATCH_ALGORITHM_VERSION,
        input_snapshot_hash=snapshot_hash,
    )
    db.add(run)
    db.flush()
    clusters = _active_clusters(db, context.run.clustering_run_id)
    memberships = _cluster_memberships(db, [item.job_cluster_version_id for item in clusters])
    signals_by_job = _signals_by_job(context.signals)
    scored = []
    for cluster in clusters:
        metrics = _cluster_capability_metrics(
            context,
            cluster,
            memberships.get(cluster.job_cluster_version_id, set()),
            signals_by_job,
            level_code="L3",
            recent_job_count=10,
        )[:20]
        if not metrics:
            continue
        scored.append(
            _score_cluster(
                context.nodes,
                version,
                cluster,
                metrics,
                profile_skill_ids,
                profile_l2,
            )
        )
    scored.sort(key=lambda item: (-item["overall_score"], item["cluster"].stable_cluster_code))
    for rank, scored_item in enumerate(scored[:limit], 1):
        cluster = scored_item["cluster"]
        representative_id = db.scalar(
            select(JobClusterMember.job_posting_id)
            .where(
                JobClusterMember.job_cluster_version_id == cluster.job_cluster_version_id,
                JobClusterMember.is_representative.is_(True),
            )
            .limit(1)
        )
        if representative_id is None:
            representative_id = db.scalar(
                select(JobClusterMember.job_posting_id)
                .where(JobClusterMember.job_cluster_version_id == cluster.job_cluster_version_id)
                .order_by(JobClusterMember.similarity_score.desc())
                .limit(1)
            )
        result = CandidateMatchResult(
            candidate_match_run_id=run.candidate_match_run_id,
            result_code=f"CMRSLT-{uuid4().hex[:16]}",
            job_cluster_version_id=cluster.job_cluster_version_id,
            representative_job_posting_id=representative_id,
            rank_no=rank,
            overall_score=Decimal(str(scored_item["overall_score"])),
            confidence_score=Decimal(str(scored_item["confidence_score"])),
            dimension_json=scored_item["dimensions"],
            recommendation_json={
                "reasons": scored_item["reasons"],
                "warning": "未出现在简历中的技能只标记为证据不足。",
            },
        )
        db.add(result)
        db.flush()
        for gap in scored_item["gaps"]:
            db.add(
                CandidateMatchGap(
                    candidate_match_result_id=result.candidate_match_result_id,
                    technology_node_id=gap["technology_node_id"],
                    gap_type_code=gap["gap_type_code"],
                    importance_score=Decimal(str(gap["importance_score"])),
                    candidate_evidence_json=gap["candidate_evidence"],
                    job_evidence_json=gap["job_evidence"],
                    transfer_from_technology_node_id=gap.get("transfer_from_technology_node_id"),
                    explanation_text=gap["explanation"],
                )
            )
    run.result_count = min(limit, len(scored))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = db.scalar(
            select(CandidateMatchRun).where(
                CandidateMatchRun.candidate_profile_version_id
                == version.candidate_profile_version_id,
                CandidateMatchRun.clustering_run_id == context.run.clustering_run_id,
                CandidateMatchRun.algorithm_version == MATCH_ALGORITHM_VERSION,
                CandidateMatchRun.input_snapshot_hash == snapshot_hash,
            )
        )
        if concurrent is None:
            raise
        return match_run_snapshot(db, concurrent)
    return match_run_snapshot(db, run)


def create_learning_path(db: Session, *, result_code: str) -> dict:
    result = db.scalar(
        select(CandidateMatchResult).where(CandidateMatchResult.result_code == result_code)
    )
    if result is None:
        raise TalentWorkflowError("匹配结果不存在")
    existing = db.scalar(
        select(CandidateLearningPath).where(
            CandidateLearningPath.candidate_match_result_id == result.candidate_match_result_id,
            CandidateLearningPath.version_no == 1,
        )
    )
    if existing:
        return learning_path_snapshot(existing)
    gaps = list(
        db.scalars(
            select(CandidateMatchGap)
            .where(CandidateMatchGap.candidate_match_result_id == result.candidate_match_result_id)
            .order_by(CandidateMatchGap.importance_score.desc())
        )
    )
    nodes = {
        item.technology_node_id: item
        for item in db.scalars(
            select(TechnologyNode).where(
                TechnologyNode.technology_node_id.in_(
                    [gap.technology_node_id for gap in gaps] or [-1]
                )
            )
        )
    }
    steps = []
    for index, gap in enumerate(gaps[:5], 1):
        node = nodes[gap.technology_node_id]
        steps.append(
            {
                "step_no": index,
                "technology_node_id": node.technology_node_id,
                "technology_name": node.technology_name,
                "gap_id": gap.candidate_match_gap_id,
                "gap_type_code": gap.gap_type_code,
                "depends_on": [index - 1] if index > 1 else [],
                "learning_focus": f"补齐{node.technology_name}的核心概念、工具链和工程边界",
                "practice_task": f"完成一个可复现的{node.technology_name}具身智能小实验",
                "verification": "提交代码、实验记录、关键指标和失败复盘",
                "estimated_weeks": 2 if gap.gap_type_code == "transferable" else 3,
                "improves_dimension": "required_skill_coverage",
                "evidence_reference": f"gap:{gap.candidate_match_gap_id}",
            }
        )
    path = CandidateLearningPath(
        path_code=f"CLP-{uuid4().hex[:18]}",
        candidate_match_result_id=result.candidate_match_result_id,
        algorithm_version=PATH_ALGORITHM_VERSION,
        summary_text=f"由{len(steps)}项可追溯差距生成，完成后重新提交项目证据并重算匹配。",
        steps_json=steps,
    )
    db.add(path)
    db.commit()
    return learning_path_snapshot(path)


def profile_snapshot(
    db: Session,
    version: CandidateProfileVersion,
    *,
    next_question: CandidateDialogueTurn | None = None,
) -> dict:
    profile = db.get(CandidateProfile, version.candidate_profile_id)
    document = db.get(ResumeDocument, version.resume_document_id)
    summary = _profile_summary(db, version, profile, document)
    summary.update(
        {
            "experience_summary": version.experience_summary,
            "preferences": version.preference_json,
            "facts": version.fact_json,
            "insights": version.insight_json,
            "skills": _skill_snapshots(db, version.candidate_profile_version_id),
            "next_question": _question_snapshot(next_question),
            "can_publish": version.conversation_round_count >= MIN_DIALOGUE_ROUNDS,
            "minimum_rounds": MIN_DIALOGUE_ROUNDS,
            "maximum_rounds": MAX_DIALOGUE_ROUNDS,
        }
    )
    return summary


def match_run_snapshot(db: Session, run: CandidateMatchRun) -> dict:
    rows = db.execute(
        select(CandidateMatchResult, JobClusterVersion, JobPosting)
        .join(
            JobClusterVersion,
            JobClusterVersion.job_cluster_version_id == CandidateMatchResult.job_cluster_version_id,
        )
        .outerjoin(
            JobPosting,
            JobPosting.job_posting_id == CandidateMatchResult.representative_job_posting_id,
        )
        .where(CandidateMatchResult.candidate_match_run_id == run.candidate_match_run_id)
        .order_by(CandidateMatchResult.rank_no)
    ).all()
    results = []
    for result, cluster, posting in rows:
        gaps = list(
            db.scalars(
                select(CandidateMatchGap)
                .where(
                    CandidateMatchGap.candidate_match_result_id == result.candidate_match_result_id
                )
                .order_by(CandidateMatchGap.importance_score.desc())
            )
        )
        node_ids = [gap.technology_node_id for gap in gaps]
        nodes = {
            node.technology_node_id: node
            for node in db.scalars(
                select(TechnologyNode).where(
                    TechnologyNode.technology_node_id.in_(node_ids or [-1])
                )
            )
        }
        results.append(
            {
                "result_code": result.result_code,
                "rank_no": result.rank_no,
                "overall_score": float(result.overall_score),
                "confidence_score": float(result.confidence_score),
                "cluster_code": cluster.stable_cluster_code,
                "job_title": cluster.cluster_label,
                "representative_jd": {
                    "job_code": posting.job_code if posting else None,
                    "company": posting.company_name_raw if posting else None,
                    "region": posting.region_text if posting else None,
                    "job_level": posting.job_level_code if posting else None,
                },
                "dimensions": result.dimension_json,
                "recommendation": result.recommendation_json,
                "gaps": [
                    {
                        "gap_id": gap.candidate_match_gap_id,
                        "technology_node_id": gap.technology_node_id,
                        "technology_name": nodes[gap.technology_node_id].technology_name,
                        "gap_type_code": gap.gap_type_code,
                        "importance_score": float(gap.importance_score),
                        "candidate_evidence": gap.candidate_evidence_json,
                        "job_evidence": gap.job_evidence_json,
                        "explanation": gap.explanation_text,
                    }
                    for gap in gaps
                ],
            }
        )
    return {
        "run_code": run.run_code,
        "profile_version_code": _get_version_by_id(
            db, run.candidate_profile_version_id
        ).version_code,
        "algorithm_version": run.algorithm_version,
        "result_count": run.result_count,
        "results": results,
    }


def learning_path_snapshot(path: CandidateLearningPath) -> dict:
    return {
        "path_code": path.path_code,
        "match_result_id": path.candidate_match_result_id,
        "version_no": path.version_no,
        "algorithm_version": path.algorithm_version,
        "summary": path.summary_text,
        "steps": path.steps_json,
        "workflow_status_code": path.workflow_status_code,
    }


def _extract_skill_evidence(db: Session, version: CandidateProfileVersion, text: str) -> None:
    active_nodes = list(
        db.scalars(select(TechnologyNode).where(TechnologyNode.governance_status_code == "active"))
    )
    node_by_id = {node.technology_node_id: node for node in active_nodes}
    aliases = db.execute(
        select(TechnologyAlias, TechnologyNode)
        .join(
            TechnologyNode,
            TechnologyNode.technology_node_id == TechnologyAlias.technology_node_id,
        )
        .where(
            TechnologyAlias.is_matchable.is_(True),
            TechnologyNode.governance_status_code == "active",
        )
    ).all()
    lower_text = text.casefold()
    best = {}
    for alias, node in aliases:
        term = alias.alias_text.strip()
        if len(term) < 2 or term.casefold() not in lower_text:
            continue
        standard_node = _ancestor_node_at_level(node_by_id, node, "L3")
        if standard_node is None:
            continue
        current = best.get(standard_node.technology_node_id)
        if current is None or len(term) > len(current[0]):
            best[standard_node.technology_node_id] = (term, standard_node)
    for node in active_nodes:
        term = node.technology_name.strip()
        if node.level_code != "L3" or len(term) < 2 or term.casefold() not in lower_text:
            continue
        current = best.get(node.technology_node_id)
        if current is None or len(term) > len(current[0]):
            best[node.technology_node_id] = (term, node)
    for term, node in sorted(
        best.values(), key=lambda item: (-len(item[0]), item[1].technology_code)
    ):
        evidence = _evidence_window(text, term)
        db.add(
            CandidateSkillEvidence(
                candidate_profile_version_id=version.candidate_profile_version_id,
                technology_node_id=node.technology_node_id,
                raw_mention=term,
                evidence_text=evidence,
                source_type_code="resume_fact",
                evidence_level_code="context_mentioned",
                confidence_score=Decimal("85"),
            )
        )


def _extract_basic_facts(text: str) -> dict:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    name_match = re.search(r"(?:姓名|Name)\s*[:：]\s*([^\s|，,]{2,30})", text, re.I)
    target_match = re.search(r"(?:求职意向|目标岗位|求职目标)\s*[:：]\s*([^\n]{2,200})", text, re.I)
    education = next(
        (
            line[:500]
            for line in lines
            if any(term in line for term in ("博士", "硕士", "本科", "大专"))
        ),
        None,
    )
    display_name = name_match.group(1) if name_match else "待确认求职者"
    return {
        "display_name": display_name,
        "target_role": target_match.group(1).strip() if target_match else None,
        "education": education,
        "experience_summary": "；".join(lines[:6])[:3000],
    }


def _clean_untrusted_text(text: str) -> str:
    cleaned = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in cleaned.splitlines()).strip()


def _evidence_window(text: str, term: str, radius: int = 90) -> str:
    index = text.casefold().find(term.casefold())
    if index < 0:
        return term
    return text[max(0, index - radius) : min(len(text), index + len(term) + radius)].strip()


def _ensure_next_question(
    db: Session, version: CandidateProfileVersion
) -> CandidateDialogueTurn | None:
    asked = set(
        db.scalars(
            select(CandidateDialogueTurn.question_code).where(
                CandidateDialogueTurn.candidate_profile_version_id
                == version.candidate_profile_version_id
            )
        )
    )
    priorities = list(QUESTION_BANK)
    if version.target_role_text:
        priorities = [item for item in priorities if item[0] != "target_role"] + [
            item for item in priorities if item[0] == "target_role"
        ]
    for question_code, question_text in priorities:
        if question_code in asked:
            continue
        turn_no = len(asked) + 1
        if turn_no > MAX_DIALOGUE_ROUNDS:
            return None
        turn = CandidateDialogueTurn(
            candidate_profile_version_id=version.candidate_profile_version_id,
            turn_no=turn_no,
            question_code=question_code,
            question_text=question_text,
        )
        db.add(turn)
        db.flush()
        return turn
    return None


def _dialogue_can_finish(version: CandidateProfileVersion) -> bool:
    if version.conversation_round_count < MIN_DIALOGUE_ROUNDS:
        return False
    preferences = version.preference_json or {}
    required = bool(version.target_role_text) and "representative_project" in preferences
    return required or version.conversation_round_count >= 4


def _update_completeness(db: Session, version: CandidateProfileVersion) -> None:
    skill_count = (
        db.scalar(
            select(func.count())
            .select_from(CandidateSkillEvidence)
            .where(
                CandidateSkillEvidence.candidate_profile_version_id
                == version.candidate_profile_version_id
            )
        )
        or 0
    )
    score = 20
    score += 15 if version.target_role_text else 0
    score += 12 if version.education_text else 0
    score += min(skill_count * 3, 30)
    score += min(version.conversation_round_count * 6, 24)
    score += 8 if (version.preference_json or {}).get("representative_project") else 0
    version.completeness_score = Decimal(min(score, 100))


def _score_cluster(
    nodes: dict[int, TechnologyNode],
    version: CandidateProfileVersion,
    cluster: JobClusterVersion,
    metrics: list[dict],
    profile_skill_ids: set[int],
    profile_l2: set[int],
) -> dict:
    required_weight = sum(max(item["importance"], 1) for item in metrics)
    matched_weight = sum(
        item["importance"] for item in metrics if item["technology_node_id"] in profile_skill_ids
    )
    transferable = []
    gaps = []
    for metric in metrics:
        technology_id = metric["technology_node_id"]
        if technology_id in profile_skill_ids:
            continue
        l2_id = _ancestor_at_level(nodes, technology_id, "L2")
        transfer_from = next(
            (
                skill_id
                for skill_id in profile_skill_ids
                if l2_id is not None and _ancestor_at_level(nodes, skill_id, "L2") == l2_id
            ),
            None,
        )
        gap_type = "transferable" if transfer_from else "evidence_insufficient"
        if transfer_from:
            transferable.append(metric)
        gaps.append(
            {
                "technology_node_id": technology_id,
                "gap_type_code": gap_type,
                "importance_score": metric["importance"],
                "candidate_evidence": ([f"technology:{transfer_from}"] if transfer_from else []),
                "job_evidence": [f"job:{code}" for code in metric["evidence_job_codes"][:10]],
                "transfer_from_technology_node_id": transfer_from,
                "explanation": (
                    "候选人具备同一L2能力域的相邻技术证据，可作为迁移起点。"
                    if transfer_from
                    else "画像中暂未找到该技术的可核验证据，不等于候选人不会。"
                ),
            }
        )
    coverage = matched_weight / required_weight if required_weight else 0
    transfer_score = (
        sum(item["importance"] for item in transferable) / required_weight if required_weight else 0
    )
    target_similarity = _text_overlap(version.target_role_text or "", cluster.cluster_label)
    evidence_depth = min(1.0, len(profile_skill_ids) / 8)
    overall = _round_score(
        100
        * (
            0.40 * coverage
            + 0.10 * transfer_score
            + 0.45 * target_similarity
            + 0.05 * evidence_depth
        )
    )
    confidence = _round_score(
        min(92, 55 + len(profile_skill_ids) * 2 + min(cluster.member_count, 20))
    )
    dimensions = [
        {
            "code": "required_skill_coverage",
            "label": "必需能力覆盖",
            "score": _round_score(coverage * 100),
            "weight": 0.40,
        },
        {
            "code": "transferability",
            "label": "可迁移能力",
            "score": _round_score(transfer_score * 100),
            "weight": 0.10,
        },
        {
            "code": "target_semantics",
            "label": "求职目标语义",
            "score": _round_score(target_similarity * 100),
            "weight": 0.45,
        },
        {
            "code": "evidence_depth",
            "label": "个人证据完整度",
            "score": _round_score(evidence_depth * 100),
            "weight": 0.05,
        },
    ]
    matched_names = [
        item["technology_name"]
        for item in metrics
        if item["technology_node_id"] in profile_skill_ids
    ][:3]
    reasons = [f"已有证据覆盖：{'、'.join(matched_names)}"] if matched_names else []
    if transferable:
        reasons.append(f"存在{len(transferable)}项同能力域可迁移技术")
    if not reasons:
        reasons.append("当前主要依据求职目标和有限技术证据召回，需补充项目证据")
    return {
        "cluster": cluster,
        "overall_score": overall,
        "confidence_score": confidence,
        "dimensions": dimensions,
        "reasons": reasons,
        "gaps": sorted(gaps, key=lambda item: -item["importance_score"])[:8],
    }


def _text_overlap(left: str, right: str) -> float:
    left_tokens = set(re.findall(r"[a-z0-9+#.]+|[\u4e00-\u9fff]{2,}", left.casefold()))
    right_tokens = set(re.findall(r"[a-z0-9+#.]+|[\u4e00-\u9fff]{2,}", right.casefold()))
    if not left_tokens or not right_tokens:
        return 0.0
    if left.casefold() in right.casefold() or right.casefold() in left.casefold():
        return 1.0
    token_score = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    left_han = "".join(re.findall(r"[\u4e00-\u9fff]", left))
    right_han = "".join(re.findall(r"[\u4e00-\u9fff]", right))
    left_bigrams = {left_han[index : index + 2] for index in range(len(left_han) - 1)}
    right_bigrams = {right_han[index : index + 2] for index in range(len(right_han) - 1)}
    bigram_score = (
        len(left_bigrams & right_bigrams) / len(left_bigrams | right_bigrams)
        if left_bigrams and right_bigrams
        else 0.0
    )
    return max(token_score, bigram_score)


def _ancestor_at_level(
    nodes: dict[int, TechnologyNode], technology_id: int, level: str
) -> int | None:
    current = nodes.get(technology_id)
    visited = set()
    while current and current.technology_node_id not in visited:
        if current.level_code == level:
            return current.technology_node_id
        visited.add(current.technology_node_id)
        current = nodes.get(current.parent_technology_node_id)
    return None


def _ancestor_node_at_level(
    nodes: dict[int, TechnologyNode], node: TechnologyNode, level: str
) -> TechnologyNode | None:
    current = node
    visited = set()
    while current and current.technology_node_id not in visited:
        if current.level_code == level:
            return current
        visited.add(current.technology_node_id)
        current = nodes.get(current.parent_technology_node_id)
    return None


def _profile_summary(
    db: Session,
    version: CandidateProfileVersion,
    profile: CandidateProfile,
    document: ResumeDocument,
) -> dict:
    match_count = (
        db.scalar(
            select(func.count())
            .select_from(CandidateMatchRun)
            .where(
                CandidateMatchRun.candidate_profile_version_id
                == version.candidate_profile_version_id
            )
        )
        or 0
    )
    return {
        "profile_code": profile.profile_code,
        "version_code": version.version_code,
        "version_no": version.version_no,
        "display_name": profile.display_name,
        "source_name": document.source_name,
        "mime_type": document.mime_type,
        "workflow_status_code": version.workflow_status_code,
        "target_role_text": version.target_role_text,
        "education_text": version.education_text,
        "completeness_score": float(version.completeness_score),
        "conversation_round_count": version.conversation_round_count,
        "skill_count": len(_skills(db, version.candidate_profile_version_id)),
        "match_run_count": match_count,
        "created_at": version.created_at.isoformat(timespec="seconds"),
    }


def _skill_snapshots(db: Session, version_id: int) -> list[dict]:
    rows = db.execute(
        select(CandidateSkillEvidence, TechnologyNode)
        .join(
            TechnologyNode,
            TechnologyNode.technology_node_id == CandidateSkillEvidence.technology_node_id,
        )
        .where(CandidateSkillEvidence.candidate_profile_version_id == version_id)
        .order_by(TechnologyNode.technology_code)
    ).all()
    return [
        {
            "skill_evidence_id": evidence.candidate_skill_evidence_id,
            "technology_node_id": node.technology_node_id,
            "technology_code": node.technology_code,
            "technology_name": node.technology_name,
            "level_code": node.level_code,
            "raw_mention": evidence.raw_mention,
            "evidence_text": evidence.evidence_text,
            "source_type_code": evidence.source_type_code,
            "evidence_level_code": evidence.evidence_level_code,
            "confidence_score": float(evidence.confidence_score),
            "user_confirmed": evidence.user_confirmed,
        }
        for evidence, node in rows
    ]


def _question_snapshot(turn: CandidateDialogueTurn | None) -> dict | None:
    if turn is None:
        return None
    return {
        "turn_no": turn.turn_no,
        "question_code": turn.question_code,
        "question_text": turn.question_text,
    }


def _skills(db: Session, version_id: int) -> list[CandidateSkillEvidence]:
    return list(
        db.scalars(
            select(CandidateSkillEvidence)
            .where(CandidateSkillEvidence.candidate_profile_version_id == version_id)
            .order_by(CandidateSkillEvidence.candidate_skill_evidence_id)
        )
    )


def _get_version(db: Session, version_code: str) -> CandidateProfileVersion:
    version = db.scalar(
        select(CandidateProfileVersion).where(CandidateProfileVersion.version_code == version_code)
    )
    if version is None:
        raise TalentWorkflowError("求职者画像版本不存在")
    return version


def _get_version_by_id(db: Session, version_id: int) -> CandidateProfileVersion:
    version = db.get(CandidateProfileVersion, version_id)
    if version is None:
        raise TalentWorkflowError("求职者画像版本不存在")
    return version


def _round_score(value: float) -> float:
    return float(
        Decimal(str(max(0, min(100, value)))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )
