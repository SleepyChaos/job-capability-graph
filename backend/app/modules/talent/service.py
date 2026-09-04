import hashlib
import json
import re
from collections import defaultdict
from datetime import date, datetime
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
from app.modules.job.models import JobPosting, JobRequirement
from app.modules.talent.acquisition import (
    AcquisitionCosts,
    ScoreProjection,
    plan_evidence_questions,
    plan_minimal_improvement_sets,
)
from app.modules.talent.evidence_state import EvidenceState, EvidenceValue
from app.modules.talent.models import (
    CandidateDialogueTurn,
    CandidateLearningPath,
    CandidateMatchDimensionResult,
    CandidateMatchGap,
    CandidateMatchResult,
    CandidateMatchRun,
    CandidateProfile,
    CandidateProfileVersion,
    CandidateSkillEvidence,
    JobRequirementExpression,
    ResumeDocument,
)
from app.modules.talent.requirement_dsl import (
    RequirementContext,
    RequirementNode,
    compile_flat_requirements,
    evaluate_requirement,
)
from app.modules.talent.resume_extraction import extract_resume_facts
from app.modules.taxonomy.models import TechnologyAlias, TechnologyNode

MATCH_ALGORITHM_VERSION = "r_daea_pjf_v3"
PATH_ALGORITHM_VERSION = "gap_path_topo_v1"
MIN_DIALOGUE_ROUNDS = 2
MAX_DIALOGUE_ROUNDS = 8
QUESTION_VALUE_THRESHOLD = 0.05
MATCH_DECISION_THRESHOLD = 60.0
HARD_CONSTRAINT_SCORE_CAP = 59.0
MAX_EVIDENCE_ACQUISITION_ROUNDS = 4
EVIDENCE_QUESTION_VALUE_THRESHOLD = 0.08

# 设计文档 §13.2 的 10 维匹配权重，权重调整必须同步修改算法版本号。
MATCH_DIMENSIONS = (
    ("required_capability_fit", "必需能力覆盖", 0.34),
    ("bonus_capability_fit", "加分能力覆盖", 0.10),
    ("proficiency_fit", "技能深度与熟练度", 0.12),
    ("task_semantic_fit", "任务语义匹配", 0.12),
    ("project_evidence_fit", "项目证据", 0.08),
    ("recency_fit", "时间新鲜度", 0.07),
    ("scenario_fit", "行业与场景", 0.06),
    ("level_fit", "岗位级别", 0.05),
    ("transferable_fit", "可迁移能力", 0.04),
    ("confirmed_preference_fit", "已确认职业意向", 0.02),
)

GAP_TYPE_LABELS = {
    "confirmed_missing": "已确认缺失",
    "evidence_insufficient": "证据不足",
    "depth_insufficient": "掌握深度不足",
    "transferable": "具备可迁移的相邻能力",
    "low_confidence_requirement": "岗位要求本身置信度不足",
}


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

# question_value = impact_on_match × uncertainty × answerability − privacy_risk − repetition_penalty
QUESTION_VALUE_FACTORS = {
    "target_role": {"impact": 0.90, "answerability": 0.90, "privacy_risk": 0.05},
    "representative_project": {"impact": 0.85, "answerability": 0.85, "privacy_risk": 0.05},
    "work_preference": {"impact": 0.60, "answerability": 0.90, "privacy_risk": 0.05},
    "target_level": {"impact": 0.70, "answerability": 0.90, "privacy_risk": 0.05},
    "target_scenario": {"impact": 0.65, "answerability": 0.90, "privacy_risk": 0.05},
    "development_horizon": {"impact": 0.50, "answerability": 0.90, "privacy_risk": 0.05},
    "constraints": {"impact": 0.40, "answerability": 0.60, "privacy_risk": 0.20},
    "additional_evidence": {"impact": 0.75, "answerability": 0.85, "privacy_risk": 0.05},
}


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
    facts = extract_resume_facts(text)
    parser_version = facts["parser_version"]
    document = ResumeDocument(
        document_code=f"RES-{uuid4().hex[:20]}",
        source_name=source_name.strip() or "粘贴文本简历",
        mime_type=mime_type,
        input_type_code=input_type_code,
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        content_text=text,
        parser_version=parser_version,
    )
    db.add(document)
    db.flush()
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
            "structured": facts["structured_facts"],
            "resume_keywords": facts["skill_mentions"] or [],
            "extraction": facts["extraction"],
        },
        insight_json={
            "status": "draft_hypothesis",
            "statements": [],
            "warning": "洞察只基于可见证据和用户补充，不进行人格判定。",
        },
        completeness_score=Decimal("0"),
        parser_version=parser_version,
    )
    db.add(version)
    db.flush()
    _extract_skill_evidence(
        db,
        version,
        text,
        skill_mentions=facts["skill_mentions"],
    )
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
        .where(CandidateProfile.profile_status_code != "deleted")
        .order_by(CandidateProfileVersion.created_at.desc())
    ).all()
    return [_profile_summary(db, version, profile, document) for version, profile, document in rows]


def delete_profile_family(db: Session, *, version_code: str) -> dict:
    """隐私删除请求（设计 §17.2）：软删整个画像族，派生结果保留但不再展示。

    Q9 待确认保存期限；当前实现为用户请求即软删。
    """
    version = _get_version(db, version_code)
    profile = db.get(CandidateProfile, version.candidate_profile_id)
    if profile is None:
        raise TalentWorkflowError("求职者画像不存在")
    if profile.profile_status_code == "deleted":
        return {"profile_code": profile.profile_code, "already_deleted": True}
    profile.profile_status_code = "deleted"
    affected = 0
    for item in db.scalars(
        select(CandidateProfileVersion).where(
            CandidateProfileVersion.candidate_profile_id == profile.candidate_profile_id
        )
    ):
        if item.workflow_status_code != "deleted":
            item.workflow_status_code = "deleted"
            affected += 1
    db.commit()
    return {"profile_code": profile.profile_code, "already_deleted": False, "versions": affected}


def mask_display_name(name: str | None) -> str:
    if not name:
        return "未命名"
    if len(name) <= 1:
        return name
    if len(name) == 2:
        return f"{name[0]}*"
    return f"{name[0]}{'*' * (len(name) - 2)}{name[-1]}"


def export_profiles_masked(db: Session) -> list[dict]:
    """脱敏导出（设计 §17.2）：仅输出统计所需最小字段，姓名脱敏。"""
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
        .where(CandidateProfile.profile_status_code != "deleted")
        .order_by(CandidateProfileVersion.created_at.desc())
    ).all()
    export = []
    for version, profile, document in rows:
        export.append(
            {
                "version_code": version.version_code,
                "display_name_masked": mask_display_name(profile.display_name),
                "workflow_status_code": version.workflow_status_code,
                "skill_count": len(_skills(db, version.candidate_profile_version_id)),
                "completeness_score": float(version.completeness_score),
                "conversation_round_count": version.conversation_round_count,
                "input_type_code": document.input_type_code,
                "created_at": version.created_at.isoformat(timespec="seconds"),
            }
        )
    return export


def get_profile(db: Session, *, version_code: str) -> dict:
    return profile_snapshot(db, _get_version(db, version_code))


def get_match_evidence_question(db: Session, *, result_code: str) -> dict:
    """返回机械规划器选择的下一条岗位相关证据问题，不调用 LLM。"""
    result = _get_match_result(db, result_code)
    recommendation = result.recommendation_json or {}
    return {
        "result_code": result.result_code,
        "decision": recommendation.get("decision"),
        "score_interval": recommendation.get("score_interval"),
        "next_evidence_question": recommendation.get("next_evidence_question"),
        "minimal_improvement_sets": recommendation.get(
            "minimal_improvement_sets", []
        ),
        "can_answer": recommendation.get("next_evidence_question") is not None,
        "planner_version": MATCH_ALGORITHM_VERSION,
        "llm_used_for_selection": False,
    }


def answer_match_evidence_question(
    db: Session,
    *,
    result_code: str,
    answer_text: str,
    limit: int = 5,
) -> dict:
    """把岗位相关补证回答写入新画像版本并重算，保持已发布版本不可变。"""
    result = _get_match_result(db, result_code)
    recommendation = result.recommendation_json or {}
    question = recommendation.get("next_evidence_question")
    if not isinstance(question, dict):
        raise TalentWorkflowError("该匹配结果当前不需要或无法继续补充证据")
    answer = answer_text.strip()
    if not answer:
        raise TalentWorkflowError("回答不能为空")
    technology_id = int(question["technology_node_id"])
    run = db.get(CandidateMatchRun, result.candidate_match_run_id)
    if run is None:
        raise TalentWorkflowError("匹配运行不存在")
    previous = _get_version_by_id(db, run.candidate_profile_version_id)
    evidence_state = _classify_evidence_answer(answer)
    max_version = (
        db.scalar(
            select(func.max(CandidateProfileVersion.version_no)).where(
                CandidateProfileVersion.candidate_profile_id == previous.candidate_profile_id
            )
        )
        or 0
    )
    fact_json = json.loads(json.dumps(previous.fact_json or {}, ensure_ascii=False))
    acquisition = dict(fact_json.get("evidence_acquisition") or {})
    missing_ids = {
        int(item) for item in acquisition.get("confirmed_missing_technology_ids", [])
    }
    if evidence_state == "confirmed_missing":
        missing_ids.add(technology_id)
    else:
        missing_ids.discard(technology_id)
    history = list(acquisition.get("history") or [])
    history.append(
        {
            "source_result_code": result.result_code,
            "cluster_code": question.get("cluster_code"),
            "question_code": question.get("question_code"),
            "technology_node_id": technology_id,
            "technology_name": question.get("technology_name"),
            "answer_text": answer[:5000],
            "evidence_state": evidence_state,
            "planner_version": MATCH_ALGORITHM_VERSION,
            "recorded_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    acquisition["confirmed_missing_technology_ids"] = sorted(missing_ids)
    acquisition["history"] = history
    fact_json["evidence_acquisition"] = acquisition
    version = CandidateProfileVersion(
        candidate_profile_id=previous.candidate_profile_id,
        resume_document_id=previous.resume_document_id,
        version_code=f"CPV-{uuid4().hex[:18]}",
        version_no=max_version + 1,
        previous_version_id=previous.candidate_profile_version_id,
        workflow_status_code="confirmed",
        target_role_text=previous.target_role_text,
        education_text=previous.education_text,
        experience_summary=previous.experience_summary,
        preference_json=json.loads(
            json.dumps(previous.preference_json or {}, ensure_ascii=False)
        ),
        fact_json=fact_json,
        insight_json={
            "status": "evidence_acquisition_update",
            "statements": [
                {
                    "text": (
                        f"针对{question.get('technology_name', '岗位能力')}补充了"
                        f"{_evidence_state_label(evidence_state)}。"
                    ),
                    "source": "user_supplement",
                    "evidence_ids": [f"match:{result.result_code}"],
                }
            ],
            "warning": "补充回答按证据等级进入机械评分；自我声明不会直接获得满分。",
        },
        completeness_score=previous.completeness_score,
        conversation_round_count=previous.conversation_round_count + 1,
        parser_version=previous.parser_version,
        published_at=datetime.now(),
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
    if evidence_state != "confirmed_missing":
        db.add(
            CandidateSkillEvidence(
                candidate_profile_version_id=version.candidate_profile_version_id,
                technology_node_id=technology_id,
                raw_mention=str(question.get("technology_name") or "补充能力证据")[:500],
                evidence_text=answer,
                source_type_code="dialogue_evidence",
                evidence_level_code=evidence_state,
                confidence_score=Decimal(
                    "88" if evidence_state == "contextual" else "60"
                ),
                user_confirmed=True,
            )
        )
    db.add(
        CandidateDialogueTurn(
            candidate_profile_version_id=version.candidate_profile_version_id,
            turn_no=version.conversation_round_count,
            question_code=str(question.get("question_code") or "match_evidence")[:64],
            question_text=str(question.get("question_text") or "请补充岗位能力证据"),
            answer_text=answer,
            answer_source_code="match_evidence_acquisition",
        )
    )
    _update_completeness(db, version)
    db.commit()
    updated_profile = profile_snapshot(db, version)
    updated_match = run_matching(db, version_code=version.version_code, limit=limit)
    return {
        "source_result_code": result.result_code,
        "evidence_update": {
            "technology_node_id": technology_id,
            "technology_name": question.get("technology_name"),
            "evidence_state": evidence_state,
            "mechanical_confidence": 88.0 if evidence_state == "contextual" else (
                0.0 if evidence_state == "confirmed_missing" else 60.0
            ),
        },
        "profile": updated_profile,
        "match": updated_match,
    }


def run_matching(db: Session, *, version_code: str, limit: int = 5) -> dict:
    version = _get_version(db, version_code)
    if version.workflow_status_code != "confirmed":
        raise TalentWorkflowError("只有已确认画像可以发起岗位匹配")
    context = _context(db)
    profile_skills = _skills(db, version.candidate_profile_version_id)
    profile_skill_map = {item.technology_node_id: item for item in profile_skills}
    snapshot_payload = {
        "version_code": version.version_code,
        "skills": [
            {
                "technology_node_id": item.technology_node_id,
                "evidence_level": item.evidence_level_code,
                "confidence": float(item.confidence_score),
                "user_confirmed": item.user_confirmed,
                "evidence_text_hash": hashlib.sha256(
                    (item.evidence_text or "").encode("utf-8")
                ).hexdigest(),
            }
            for item in profile_skills
        ],
        "confirmed_missing_technology_ids": sorted(
            _confirmed_missing_technology_ids(version)
        ),
        "target_role": version.target_role_text,
        "clustering_run": context.run.run_code,
        "reference_date": context.run.target_date.isoformat(),
        "requirement_expressions": _requirement_expression_snapshot(
            db,
            context.run.clustering_run_id,
        ),
    }
    snapshot_hash = hashlib.sha256(
        json.dumps(
            snapshot_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
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
        member_ids = memberships.get(cluster.job_cluster_version_id, set())
        metrics = _cluster_capability_metrics(
            context,
            cluster,
            member_ids,
            signals_by_job,
            level_code="L3",
            recent_job_count=10,
        )[:20]
        if not metrics:
            continue
        scored.append(
            _score_cluster(
                db,
                context.nodes,
                version,
                cluster,
                metrics,
                member_ids,
                profile_skill_map,
                reference_date=context.run.target_date,
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
                "warning": (
                    "未出现在简历中的技能只进入未知区间；只有用户明确否认且属于高置信必备要求时才触发硬门槛。"
                ),
                "decision": scored_item["decision"],
                "score_interval": scored_item["score_interval"],
                "hard_constraints": scored_item["hard_constraints"],
                "requirement_expression": scored_item["requirement_expression"],
                "requirement_proof": scored_item["requirement_proof"],
                "acquisition_policy": scored_item["acquisition_policy"],
                "next_evidence_question": scored_item["next_evidence_question"],
                "evidence_question_candidates": scored_item[
                    "evidence_question_candidates"
                ],
                "minimal_improvement_sets": scored_item[
                    "minimal_improvement_sets"
                ],
            },
        )
        db.add(result)
        db.flush()
        for dimension in scored_item["dimensions"]:
            db.add(
                CandidateMatchDimensionResult(
                    candidate_match_result_id=result.candidate_match_result_id,
                    dimension_code=dimension["code"],
                    dimension_label=dimension["label"],
                    raw_score=Decimal(str(dimension["score"])),
                    weight=Decimal(str(dimension["weight"])),
                    contribution=Decimal(str(dimension["contribution"])),
                    status_code=dimension["status"],
                    explanation_json={
                        "lower_score": dimension.get("lower_score", dimension["score"]),
                        "upper_score": dimension.get("upper_score", dimension["score"]),
                    },
                )
            )
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


def save_job_requirement_expression(
    db: Session,
    *,
    job_cluster_version_id: int,
    expression_payload: dict,
) -> dict:
    """Validate and append an immutable human-confirmed requirement version."""
    cluster = db.get(JobClusterVersion, job_cluster_version_id)
    if cluster is None:
        raise TalentWorkflowError("岗位簇版本不存在")
    try:
        expression = RequirementNode.from_dict(expression_payload)
    except (TypeError, ValueError, KeyError) as exc:
        raise TalentWorkflowError(f"岗位规则表达式无效：{exc}") from exc
    active_technology_ids = set(
        db.scalars(
            select(TechnologyNode.technology_node_id).where(
                TechnologyNode.technology_node_id.in_(expression.technology_ids),
                TechnologyNode.governance_status_code == "active",
            )
        )
    )
    missing_ids = sorted(set(expression.technology_ids) - active_technology_ids)
    if missing_ids:
        raise TalentWorkflowError(f"岗位规则引用了不存在或未启用的技术节点：{missing_ids}")
    latest_version = db.scalar(
        select(func.max(JobRequirementExpression.expression_version_no)).where(
            JobRequirementExpression.job_cluster_version_id == job_cluster_version_id
        )
    )
    record = JobRequirementExpression(
        job_cluster_version_id=job_cluster_version_id,
        expression_version_no=int(latest_version or 0) + 1,
        expression_json=expression.to_dict(),
        workflow_status_code="confirmed",
        source_type_code="human_annotation",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {
        "job_requirement_expression_id": record.job_requirement_expression_id,
        "job_cluster_version_id": record.job_cluster_version_id,
        "expression_version_no": record.expression_version_no,
        "expression": record.expression_json,
        "workflow_status_code": record.workflow_status_code,
        "source_type_code": record.source_type_code,
    }


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
    steps, topo_note = _topological_steps(gaps[:6], nodes)
    path = CandidateLearningPath(
        path_code=f"CLP-{uuid4().hex[:18]}",
        candidate_match_result_id=result.candidate_match_result_id,
        algorithm_version=PATH_ALGORITHM_VERSION,
        summary_text=(
            f"由{len(steps)}项可追溯差距经拓扑排序生成{topo_note}，"
            "完成后重新提交项目证据并重算匹配。"
        ),
        steps_json=steps,
    )
    db.add(path)
    db.commit()
    return learning_path_snapshot(path)


def _topological_steps(
    gaps: list[CandidateMatchGap], nodes: dict[int, TechnologyNode]
) -> tuple[list[dict], str]:
    """按依赖关系对差距步骤做 Kahn 拓扑排序，检测并记录循环依赖。

    依赖来源：
    1. 可迁移差距的迁移源技术若也是待补差距，则先学迁移源；
    2. 同一 L2 能力域内的差距按重要度从高到低串行。
    """
    if not gaps:
        return [], ""
    index_by_tech = {gap.technology_node_id: idx for idx, gap in enumerate(gaps)}
    depends: dict[int, set[int]] = {idx: set() for idx in range(len(gaps))}
    for idx, gap in enumerate(gaps):
        source = gap.transfer_from_technology_node_id
        if source is not None and source in index_by_tech and index_by_tech[source] != idx:
            depends[idx].add(index_by_tech[source])
    groups: dict[int | None, list[int]] = defaultdict(list)
    for idx, gap in enumerate(gaps):
        node = nodes.get(gap.technology_node_id)
        l2 = None
        visited = set()
        current = node
        while current and current.technology_node_id not in visited:
            if current.level_code == "L2":
                l2 = current.technology_node_id
                break
            visited.add(current.technology_node_id)
            current = nodes.get(current.parent_technology_node_id)
        groups[l2].append(idx)
    for members in groups.values():
        ordered = sorted(members, key=lambda idx: (-float(gaps[idx].importance_score), idx))
        for prev_idx, next_idx in zip(ordered, ordered[1:], strict=False):
            depends[next_idx].add(prev_idx)

    # Kahn 拓扑排序 + 循环依赖检测
    in_degree = {idx: len(deps) for idx, deps in depends.items()}
    dependents: dict[int, list[int]] = defaultdict(list)
    for idx, deps in depends.items():
        for dep in deps:
            dependents[dep].append(idx)
    ready = sorted(
        (idx for idx, degree in in_degree.items() if degree == 0),
        key=lambda idx: (-float(gaps[idx].importance_score), idx),
    )
    order: list[int] = []
    cycle_detected = False
    while ready:
        idx = ready.pop(0)
        order.append(idx)
        for dependent in dependents[idx]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                ready.append(dependent)
        ready.sort(key=lambda item: (-float(gaps[item].importance_score), item))
    if len(order) < len(gaps):
        cycle_detected = True
        remaining = sorted(
            (idx for idx in range(len(gaps)) if idx not in set(order)),
            key=lambda idx: (-float(gaps[idx].importance_score), idx),
        )
        order.extend(remaining)
    position = {idx: position_no for position_no, idx in enumerate(order)}
    steps = []
    for step_no, idx in enumerate(order, 1):
        gap = gaps[idx]
        node = nodes[gap.technology_node_id]
        steps.append(
            {
                "step_no": step_no,
                "technology_node_id": node.technology_node_id,
                "technology_name": node.technology_name,
                "gap_id": gap.candidate_match_gap_id,
                "gap_type_code": gap.gap_type_code,
                "depends_on": sorted(
                    position[dep] + 1 for dep in depends[idx] if dep in position
                ),
                "learning_focus": f"补齐{node.technology_name}的核心概念、工具链和工程边界",
                "practice_task": f"完成一个可复现的{node.technology_name}具身智能小实验",
                "verification": "提交代码、实验记录、关键指标和失败复盘",
                "estimated_weeks": 2 if gap.gap_type_code == "transferable" else 3,
                "improves_dimension": "required_capability_fit",
                "evidence_reference": f"gap:{gap.candidate_match_gap_id}",
            }
        )
    note = "（检测到循环依赖，已按重要度强制断开并记录）" if cycle_detected else ""
    return steps, note


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
        dimension_rows = list(
            db.scalars(
                select(CandidateMatchDimensionResult)
                .where(
                    CandidateMatchDimensionResult.candidate_match_result_id
                    == result.candidate_match_result_id
                )
                .order_by(CandidateMatchDimensionResult.match_dimension_result_id)
            )
        )
        dimensions = (
            [
                {
                    "code": item.dimension_code,
                    "label": item.dimension_label,
                    "score": float(item.raw_score),
                    "lower_score": float(
                        (item.explanation_json or {}).get("lower_score", item.raw_score)
                    ),
                    "upper_score": float(
                        (item.explanation_json or {}).get("upper_score", item.raw_score)
                    ),
                    "weight": float(item.weight),
                    "contribution": float(item.contribution),
                    "status": item.status_code,
                }
                for item in dimension_rows
            ]
            if dimension_rows
            else result.dimension_json
        )
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
                "score_interval": (result.recommendation_json or {}).get(
                    "score_interval"
                ),
                "decision": (result.recommendation_json or {}).get("decision"),
                "cluster_code": cluster.stable_cluster_code,
                "job_title": cluster.cluster_label,
                "representative_jd": {
                    "job_code": posting.job_code if posting else None,
                    "company": posting.company_name_raw if posting else None,
                    "region": posting.region_text if posting else None,
                    "job_level": posting.job_level_code if posting else None,
                },
                "dimensions": dimensions,
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


MATCH_EXPLANATION_PROMPT_VERSION = "match_explanation_v1"


def match_explanation(db: Session, *, result_code: str) -> dict:
    """匹配解释：LLM 可用时组织语言，否则规则降级（设计 §11.3、§12.1）。

    LLM 只组织确定性评分与证据，不修改机械总分。
    """
    result = db.scalar(
        select(CandidateMatchResult).where(CandidateMatchResult.result_code == result_code)
    )
    if result is None:
        raise TalentWorkflowError("匹配结果不存在")
    dimensions = result.dimension_json or []
    gaps = list(
        db.scalars(
            select(CandidateMatchGap)
            .where(CandidateMatchGap.candidate_match_result_id == result.candidate_match_result_id)
            .order_by(CandidateMatchGap.importance_score.desc())
        )
    )
    rule_text = _rule_match_explanation(result, dimensions, gaps)
    llm_text = _llm_match_explanation(result, dimensions, gaps)
    return {
        "result_code": result.result_code,
        "explanation_text": llm_text or rule_text,
        "generation_method": "llm_explanation" if llm_text else "rule_explanation",
        "model_version": (
            f"llm:{_llm_model_name()}" if llm_text else "rule_explanation_v1"
        ),
    }


def _llm_model_name() -> str:
    from app.core.config import get_settings

    return get_settings().llm_model


def _llm_match_explanation(result, dimensions: list[dict], gaps) -> str | None:
    from app.infrastructure.llm import generate

    facts = {
        "overall_score": float(result.overall_score),
        "score_interval": (result.recommendation_json or {}).get("score_interval"),
        "decision": (result.recommendation_json or {}).get("decision"),
        "dimensions": [
            {"label": item.get("label"), "score": item.get("score"), "weight": item.get("weight")}
            for item in dimensions
        ],
        "gaps": [
            {"gap_type": gap.gap_type_code, "importance": float(gap.importance_score)}
            for gap in gaps[:8]
        ],
    }
    system_prompt = (
        "你是人岗匹配分析助手。只能基于给定评分与差距事实生成不超过 200 字的中文解释，"
        "不得新增事实或修改分数。"
    )
    llm_result = generate(
        system_prompt=system_prompt,
        user_prompt=f"匹配事实：{json.dumps(facts, ensure_ascii=False)}",
        prompt_version=MATCH_EXPLANATION_PROMPT_VERSION,
    )
    if llm_result is None:
        return None
    text = llm_result.content.strip()
    if not text or len(text) > 1000:
        return None
    return text


def _rule_match_explanation(result, dimensions: list[dict], gaps) -> str:
    ranked = sorted(dimensions, key=lambda item: -float(item.get("contribution", 0)))
    top_labels = "、".join(str(item.get("label", item.get("code"))) for item in ranked[:3])
    gap_summary = (
        f"主要差距 {len(gaps)} 项，最高重要度 {float(gaps[0].importance_score):.1f}。"
        if gaps
        else "未识别出显著差距。"
    )
    interval = (result.recommendation_json or {}).get("score_interval") or {}
    interval_text = (
        f"证据区间[{float(interval['lower']):.1f}, {float(interval['upper']):.1f}]，"
        if "lower" in interval and "upper" in interval
        else ""
    )
    return (
        f"综合匹配分 {float(result.overall_score):.1f}，{interval_text}"
        f"主要贡献维度：{top_labels}。{gap_summary}"
        "缺失证据不等于不会，补充项目证据后可重算。"
    )


def _extract_skill_evidence(
    db: Session,
    version: CandidateProfileVersion,
    text: str,
    *,
    skill_mentions: list[dict] | None = None,
) -> None:
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
    best: dict[int, tuple[str, TechnologyNode]] = {}
    llm_mentions_by_node: dict[int, dict] = {}
    if skill_mentions:
        taxonomy_lookup: dict[str, TechnologyNode] = {}
        for alias, node in aliases:
            standard_node = _ancestor_node_at_level(node_by_id, node, "L3")
            if standard_node is not None:
                taxonomy_lookup[_normalized_skill_term(alias.alias_text)] = standard_node
        for node in active_nodes:
            if node.level_code == "L3":
                taxonomy_lookup[_normalized_skill_term(node.technology_name)] = node
        for mention in skill_mentions:
            raw_name = str(mention.get("raw_name", "")).strip()
            normalized = str(mention.get("normalized_keyword", "")).strip()
            node = next(
                (
                    taxonomy_lookup.get(_normalized_skill_term(candidate))
                    for candidate in (normalized, raw_name)
                    if candidate and taxonomy_lookup.get(_normalized_skill_term(candidate))
                ),
                None,
            )
            if node is None or raw_name.casefold() not in text.casefold():
                continue
            current = best.get(node.technology_node_id)
            if current is None or len(raw_name) > len(current[0]):
                best[node.technology_node_id] = (raw_name, node)
                llm_mentions_by_node[node.technology_node_id] = mention
    if not best:
        _collect_rule_skill_matches(text, aliases, active_nodes, node_by_id, best)
    for term, node in sorted(
        best.values(), key=lambda item: (-len(item[0]), item[1].technology_code)
    ):
        mention = llm_mentions_by_node.get(node.technology_node_id)
        evidence = (
            str(mention.get("evidence_quote", "")).strip()
            if mention is not None
            else _evidence_window(text, term)
        )
        evidence_level = _resume_skill_evidence_level(evidence)
        db.add(
            CandidateSkillEvidence(
                candidate_profile_version_id=version.candidate_profile_version_id,
                technology_node_id=node.technology_node_id,
                raw_mention=term,
                evidence_text=evidence,
                source_type_code="resume_fact",
                evidence_level_code=evidence_level,
                # Fixed mechanical confidence: model confidence never enters scoring.
                confidence_score=(
                    Decimal("85") if evidence_level == "contextual" else Decimal("60")
                ),
            )
        )


def _collect_rule_skill_matches(
    text: str,
    aliases,
    active_nodes: list[TechnologyNode],
    node_by_id: dict[int, TechnologyNode],
    best: dict[int, tuple[str, TechnologyNode]],
) -> None:
    lower_text = text.casefold()
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


def _normalized_skill_term(value: str) -> str:
    return re.sub(r"[\s_\-/（）()]+", "", value.casefold()).strip()


def _resume_skill_evidence_level(evidence_text: str) -> str:
    """Deterministically distinguish a bare skill claim from contextual evidence."""
    text = evidence_text.casefold()
    action_terms = (
        "负责",
        "主导",
        "参与",
        "使用",
        "采用",
        "开发",
        "实现",
        "设计",
        "部署",
        "优化",
        "验证",
        "完成",
        "built",
        "developed",
        "implemented",
        "deployed",
    )
    context_terms = (
        "项目",
        "工作",
        "职责",
        "模块",
        "系统",
        "平台",
        "模型",
        "实验",
        "project",
        "system",
        "model",
    )
    has_action = any(term in text for term in action_terms)
    has_context = any(term in text for term in context_terms)
    return "contextual" if has_action and has_context else "self_claim"


def _clean_untrusted_text(text: str) -> str:
    cleaned = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in cleaned.splitlines()).strip()


def _evidence_window(text: str, term: str, radius: int = 90) -> str:
    index = text.casefold().find(term.casefold())
    if index < 0:
        return term
    return text[max(0, index - radius) : min(len(text), index + len(term) + radius)].strip()


def _question_known(version: CandidateProfileVersion, question_code: str) -> bool:
    if question_code == "target_role":
        return bool(version.target_role_text)
    return question_code in (version.preference_json or {})


def _question_value(version: CandidateProfileVersion, question_code: str) -> float:
    """设计 §12.3：impact × uncertainty × answerability − privacy_risk − repetition_penalty。"""
    factors = QUESTION_VALUE_FACTORS[question_code]
    uncertainty = 0.2 if _question_known(version, question_code) else 1.0
    repetition_penalty = 0.0
    return (
        factors["impact"] * uncertainty * factors["answerability"]
        - factors["privacy_risk"]
        - repetition_penalty
    )


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
    turn_no = len(asked) + 1
    if turn_no > MAX_DIALOGUE_ROUNDS:
        return None
    best: tuple[float, str, str] | None = None
    for question_code, question_text in QUESTION_BANK:
        if question_code in asked:
            continue
        value = _question_value(version, question_code)
        if best is None or value > best[0]:
            best = (value, question_code, question_text)
    if best is None or best[0] < QUESTION_VALUE_THRESHOLD:
        return None
    turn = CandidateDialogueTurn(
        candidate_profile_version_id=version.candidate_profile_version_id,
        turn_no=turn_no,
        question_code=best[1],
        question_text=best[2],
    )
    db.add(turn)
    db.flush()
    return turn


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


def _cluster_requirement_profile(
    db: Session, nodes: dict[int, TechnologyNode], member_ids: set[int]
) -> tuple[set[int], set[int], dict[int, float]]:
    """从成员 JD 的技术要求中聚合：必需技术集、加分技术集、逐技术平均置信度（投影到 L3）。"""
    if not member_ids:
        return set(), set(), {}
    rows = db.execute(
        select(
            JobRequirement.requirement_type_code,
            JobRequirement.technology_node_id,
            JobRequirement.confidence_score,
        ).where(JobRequirement.job_posting_id.in_(member_ids))
    ).all()
    required: set[int] = set()
    bonus: set[int] = set()
    confidence_acc: dict[int, list[float]] = defaultdict(list)
    for requirement_type, technology_id, confidence in rows:
        projected = _ancestor_at_level(nodes, technology_id, "L3")
        if projected is None:
            continue
        if requirement_type == "required":
            required.add(projected)
        else:
            bonus.add(projected)
        confidence_acc[projected].append(float(confidence))
    bonus -= required
    avg_confidence = {
        tech: sum(values) / len(values) for tech, values in confidence_acc.items()
    }
    return required, bonus, avg_confidence


def _evidence_state(evidence: CandidateSkillEvidence) -> str:
    level = (evidence.evidence_level_code or "").casefold()
    if level in {"verified", "externally_verified"}:
        return "verified"
    if level in {"contextual", "user_contextual", "context_mentioned", "llm_extracted"}:
        return "contextual"
    if level in {"self_claim", "user_claim"}:
        return "self_claim"
    if level == "transferable":
        return "transferable"
    if level == "contradicted":
        return "contradicted"
    if level == "confirmed_missing":
        return "confirmed_missing"
    if evidence.user_confirmed and len(evidence.evidence_text or "") >= 20:
        return "contextual"
    if evidence.user_confirmed:
        return "self_claim"
    return "contextual"


def _evidence_bounds(evidence: CandidateSkillEvidence) -> tuple[float, float]:
    """证据状态的保守/乐观能力边界；模型自报置信度不直接授权满分。"""
    state = _evidence_state(evidence)
    if state == "verified":
        return 1.0, 1.0
    if state == "contextual":
        confidence = float(evidence.confidence_score)
        lower = 0.82 if confidence >= 90 else 0.72 if confidence >= 80 else 0.60
        return lower, min(0.95, lower + 0.18)
    if state == "self_claim":
        return 0.30, 0.70
    if state == "transferable":
        return 0.15, 0.65
    if state == "contradicted":
        return 0.0, 0.25
    if state == "confirmed_missing":
        return 0.0, 0.0
    return 0.0, 0.85


_DATE_TOKEN_RE = re.compile(
    r"(?P<year>20\d{2})"
    r"(?:(?:\s*[./]\s*|\s*年\s*)(?P<month>0?[1-9]|1[0-2])\s*月?|\s*年)?",
    re.IGNORECASE,
)
_DATE_RANGE_RE = re.compile(
    r"(?P<start_year>20\d{2})"
    r"(?:(?:\s*[./]\s*|\s*年\s*)(?P<start_month>0?[1-9]|1[0-2])\s*月?|\s*年)?"
    r"\s*(?:-|–|—|~|～|至|到)\s*"
    r"(?:"
    r"(?P<end_year>20\d{2})"
    r"(?:(?:\s*[./]\s*|\s*年\s*)(?P<end_month>0?[1-9]|1[0-2])\s*月?|\s*年)?"
    r"|(?P<ongoing>至今|目前|现在|当前|present|current)"
    r")",
    re.IGNORECASE,
)
_ONGOING_RE = re.compile(r"至今|目前|现在|当前|present|current", re.IGNORECASE)


def _month_index(year: int, month: int) -> int:
    return year * 12 + month - 1


def _bounded_month_index(year: int, month: int, reference_index: int) -> int:
    """Future dates cannot manufacture extra duration or better recency."""
    return min(_month_index(year, month), reference_index)


def _evidence_timeline_bounds(
    evidence_text: str,
    reference_date: date,
) -> tuple[int | None, int | None, int | None, int | None]:
    """Extract conservative duration and recency intervals from evidence text.

    A year without a month is represented as January..December instead of being
    silently converted to one arbitrary date. Multiple ranges are not summed,
    because overlapping project/experience periods would otherwise be counted
    twice; the longest individually supported range is retained.
    """
    text = evidence_text.strip()
    if not text:
        return None, None, None, None

    reference_index = _month_index(reference_date.year, reference_date.month)
    duration_bounds: list[tuple[int, int]] = []
    for match in _DATE_RANGE_RE.finditer(text):
        start_year = int(match.group("start_year"))
        start_month_text = match.group("start_month")
        start_min = _bounded_month_index(
            start_year,
            int(start_month_text) if start_month_text else 1,
            reference_index,
        )
        start_max = _bounded_month_index(
            start_year,
            int(start_month_text) if start_month_text else 12,
            reference_index,
        )
        if match.group("ongoing"):
            end_min = end_max = reference_index
        else:
            end_year = int(match.group("end_year"))
            end_month_text = match.group("end_month")
            end_min = _bounded_month_index(
                end_year,
                int(end_month_text) if end_month_text else 1,
                reference_index,
            )
            end_max = _bounded_month_index(
                end_year,
                int(end_month_text) if end_month_text else 12,
                reference_index,
            )
        minimum = max(0, end_min - start_max + 1)
        maximum = max(minimum, end_max - start_min + 1)
        duration_bounds.append((minimum, maximum))

    if duration_bounds:
        minimum_months = max(item[0] for item in duration_bounds)
        maximum_months = max(item[1] for item in duration_bounds)
    else:
        minimum_months = maximum_months = None

    if _ONGOING_RE.search(text):
        recency_lower = recency_upper = 0
    else:
        token_bounds: list[tuple[int, int]] = []
        for match in _DATE_TOKEN_RE.finditer(text):
            year = int(match.group("year"))
            month_text = match.group("month")
            token_bounds.append(
                (
                    _bounded_month_index(
                        year,
                        int(month_text) if month_text else 1,
                        reference_index,
                    ),
                    _bounded_month_index(
                        year,
                        int(month_text) if month_text else 12,
                        reference_index,
                    ),
                )
            )
        if token_bounds:
            latest_lower = max(item[0] for item in token_bounds)
            latest_upper = max(item[1] for item in token_bounds)
            recency_lower = max(0, reference_index - latest_upper)
            recency_upper = max(recency_lower, reference_index - latest_lower)
        else:
            recency_lower = recency_upper = None

    return minimum_months, maximum_months, recency_lower, recency_upper


def _recency_score_bounds(
    evidence_text: str,
    reference_date: date,
) -> tuple[float, float] | None:
    """Map last-use uncertainty to a deterministic five-year decay interval."""
    _, _, recency_lower, recency_upper = _evidence_timeline_bounds(
        evidence_text,
        reference_date,
    )
    if recency_lower is None or recency_upper is None:
        return None

    def score(months: int) -> float:
        return max(0.10, min(1.0, 1.0 - months / 60.0))

    return score(recency_upper), score(recency_lower)


def _dsl_evidence_value(
    evidence: CandidateSkillEvidence,
    *,
    reference_date: date,
) -> EvidenceValue:
    state = EvidenceState(_evidence_state(evidence))
    lower, upper = _evidence_bounds(evidence)
    minimum_months, maximum_months, recency_lower, recency_upper = (
        _evidence_timeline_bounds(evidence.evidence_text or "", reference_date)
    )
    return EvidenceValue.for_state(
        state,
        lower=lower,
        upper=upper,
        minimum_months=minimum_months,
        maximum_months=maximum_months,
        months_since_last_use_lower=recency_lower,
        months_since_last_use_upper=recency_upper,
        source_ids=(f"skill:{evidence.candidate_skill_evidence_id}",),
    )


def _skill_strength(evidence: CandidateSkillEvidence) -> float:
    lower, upper = _evidence_bounds(evidence)
    return (lower + upper) / 2


def _is_strong_evidence(evidence: CandidateSkillEvidence) -> bool:
    return _evidence_state(evidence) in {"verified", "contextual"} and (
        float(evidence.confidence_score) >= 80
        or len(evidence.evidence_text or "") >= 80
    )


GAP_EXPLANATIONS = {
    "confirmed_missing": (
        "候选人在补充问答中明确表示不具备或不考虑该技术，按已确认缺失处理。"
    ),
    "evidence_insufficient": (
        "画像中暂未找到该技术的可核验证据，不等于候选人不会；补充项目证据后可重算。"
    ),
    "depth_insufficient": (
        "已有该技术证据但深度不足（未经用户确认且证据强度低），岗位要求为高重要度必需项。"
    ),
    "transferable": "候选人具备同一L2能力域的相邻技术证据，可作为迁移起点。",
    "low_confidence_requirement": (
        "该技术在岗位 JD 中的要求置信度偏低，建议先核实岗位要求本身。"
    ),
}


def _latest_requirement_expression(
    db: Session,
    job_cluster_version_id: int,
) -> JobRequirementExpression | None:
    return db.scalar(
        select(JobRequirementExpression)
        .where(
            JobRequirementExpression.job_cluster_version_id == job_cluster_version_id,
            JobRequirementExpression.workflow_status_code == "confirmed",
        )
        .order_by(JobRequirementExpression.expression_version_no.desc())
        .limit(1)
    )


def _requirement_expression_snapshot(db: Session, clustering_run_id: int) -> list[dict]:
    records = db.scalars(
        select(JobRequirementExpression)
        .join(
            JobClusterVersion,
            JobClusterVersion.job_cluster_version_id
            == JobRequirementExpression.job_cluster_version_id,
        )
        .where(
            JobClusterVersion.clustering_run_id == clustering_run_id,
            JobRequirementExpression.workflow_status_code == "confirmed",
        )
        .order_by(
            JobRequirementExpression.job_cluster_version_id,
            JobRequirementExpression.expression_version_no.desc(),
        )
    )
    latest_by_cluster = {}
    for record in records:
        latest_by_cluster.setdefault(
            record.job_cluster_version_id,
            {
                "job_cluster_version_id": record.job_cluster_version_id,
                "expression_version_no": record.expression_version_no,
                "expression": record.expression_json,
            },
        )
    return list(latest_by_cluster.values())


def _score_cluster(
    db: Session,
    nodes: dict[int, TechnologyNode],
    version: CandidateProfileVersion,
    cluster: JobClusterVersion,
    metrics: list[dict],
    member_ids: set[int],
    profile_skill_map: dict[int, CandidateSkillEvidence],
    *,
    reference_date: date,
) -> dict:
    metrics = list(metrics)
    profile_skill_ids = set(profile_skill_map)
    preferences = version.preference_json or {}
    confirmed_missing_ids = _confirmed_missing_technology_ids(version)
    required_tech, bonus_tech, tech_confidence = _cluster_requirement_profile(
        db, nodes, member_ids
    )
    stored_requirement = _latest_requirement_expression(
        db,
        cluster.job_cluster_version_id,
    )
    stored_expression = (
        RequirementNode.from_dict(stored_requirement.expression_json)
        if stored_requirement is not None
        else None
    )
    if stored_expression is not None:
        expression_technology_ids = set(stored_expression.technology_ids)
        required_tech.update(expression_technology_ids)
        for technology_id in expression_technology_ids:
            tech_confidence[technology_id] = max(
                tech_confidence.get(technology_id, 0.0),
                1.0,
            )
        existing_metric_ids = {int(item["technology_node_id"]) for item in metrics}
        metrics.extend(
            {
                "technology_node_id": technology_id,
                "technology_name": nodes[technology_id].technology_name,
                "importance": 1.0,
                "evidence_job_codes": [],
            }
            for technology_id in sorted(expression_technology_ids - existing_metric_ids)
            if technology_id in nodes
        )

    strict_req_metrics = [
        item for item in metrics if item["technology_node_id"] in required_tech
    ]
    req_metrics = strict_req_metrics or metrics

    def coverage_bounds(items: list[dict], minimum_weight: float) -> tuple[float, float, float]:
        total = sum(max(float(item["importance"]), minimum_weight) for item in items)
        if not total:
            return 0.0, 0.0, 0.0
        lower_sum = upper_sum = 0.0
        for item in items:
            technology_id = item["technology_node_id"]
            weight = max(float(item["importance"]), minimum_weight)
            if technology_id in confirmed_missing_ids:
                lower, upper = 0.0, 0.0
            elif technology_id in profile_skill_map:
                lower, upper = _evidence_bounds(profile_skill_map[technology_id])
            else:
                lower, upper = 0.0, 1.0
            lower_sum += weight * lower
            upper_sum += weight * upper
        lower_fit, upper_fit = lower_sum / total, upper_sum / total
        return lower_fit, upper_fit, (lower_fit + upper_fit) / 2

    requirement_expression: RequirementNode | None = None
    requirement_context: RequirementContext | None = None
    requirement_evaluation = None
    if stored_expression is not None or strict_req_metrics:
        hard_requirement_ids = {
            item["technology_node_id"]
            for item in strict_req_metrics
            if tech_confidence.get(item["technology_node_id"], 0.0) >= 0.6
        }
        requirement_expression = stored_expression or compile_flat_requirements(
            [
                (
                    int(item["technology_node_id"]),
                    max(float(item["importance"]), 1.0),
                    tuple(f"job:{code}" for code in item["evidence_job_codes"][:10]),
                )
                for item in strict_req_metrics
            ],
            hard_technology_ids=hard_requirement_ids,
        )
        requirement_skills = {
            technology_id: _dsl_evidence_value(
                evidence,
                reference_date=reference_date,
            )
            for technology_id, evidence in profile_skill_map.items()
        }
        for technology_id in confirmed_missing_ids:
            requirement_skills[technology_id] = EvidenceValue.for_state(
                EvidenceState.CONFIRMED_MISSING,
                source_ids=(f"confirmed_missing:{technology_id}",),
            )
        requirement_context = RequirementContext(skills=requirement_skills)
        requirement_evaluation = evaluate_requirement(
            requirement_expression,
            requirement_context,
        )
        required_lower = requirement_evaluation.lower
        required_upper = requirement_evaluation.upper
        required_fit = requirement_evaluation.point
    else:
        required_lower, required_upper, required_fit = coverage_bounds(req_metrics, 1.0)
    req_total = sum(max(float(item["importance"]), 1.0) for item in req_metrics)

    bonus_metrics = [item for item in metrics if item["technology_node_id"] in bonus_tech]
    if bonus_metrics:
        bonus_lower, bonus_upper, bonus_fit = coverage_bounds(bonus_metrics, 0.5)
        bonus_status = "interval_scored"
    else:
        bonus_lower = bonus_upper = bonus_fit = 0.5
        bonus_status = "neutral_unknown"

    matched_evidence = [
        profile_skill_map[item["technology_node_id"]]
        for item in metrics
        if item["technology_node_id"] in profile_skill_ids
    ]
    if matched_evidence:
        proficiency_bounds = [_evidence_bounds(item) for item in matched_evidence]
        proficiency_lower = sum(item[0] for item in proficiency_bounds) / len(
            proficiency_bounds
        )
        proficiency_upper = sum(item[1] for item in proficiency_bounds) / len(
            proficiency_bounds
        )
        proficiency_fit = (proficiency_lower + proficiency_upper) / 2
    else:
        proficiency_lower, proficiency_upper, proficiency_fit = 0.0, 0.85, 0.425

    member_rows = db.execute(
        select(JobPosting.job_title_normalized, JobPosting.job_level_code).where(
            JobPosting.job_posting_id.in_(member_ids or {-1})
        )
    ).all()
    profile_text = " ".join(
        part for part in [version.target_role_text, version.experience_summary] if part
    )
    title_texts = [title for title, _level in member_rows[:8] if title]
    task_fit = _text_overlap(profile_text, cluster.cluster_label) if profile_text else 0.5
    if profile_text and title_texts:
        task_fit = max(task_fit, _text_overlap(profile_text, " ".join(title_texts)))

    strong_evidence = [item for item in matched_evidence if _is_strong_evidence(item)]
    project_fit = len(strong_evidence) / len(matched_evidence) if matched_evidence else 0.0
    unknown_required_count = sum(
        1
        for item in req_metrics
        if item["technology_node_id"] not in profile_skill_ids
        and item["technology_node_id"] not in confirmed_missing_ids
    )
    project_lower = project_fit
    project_upper = max(
        project_lower,
        min(
            1.0,
            (len(strong_evidence) + unknown_required_count * 0.85)
            / max(1, len(matched_evidence) + unknown_required_count),
        ),
    )

    recency_ranges = [
        _recency_score_bounds(evidence.evidence_text or "", reference_date)
        for evidence in matched_evidence
    ]
    known_recency = [item for item in recency_ranges if item is not None]
    if known_recency:
        recency_lower = sum(item[0] for item in known_recency) / len(known_recency)
        recency_upper = sum(item[1] for item in known_recency) / len(known_recency)
        recency_fit = (recency_lower + recency_upper) / 2
        recency_status = "interval_scored"
    else:
        recency_lower, recency_upper = 0.0, 1.0
        recency_fit, recency_status = 0.5, "neutral_unknown"
    scenario_text = str(preferences.get("target_scenario", {}).get("value", "")).strip()
    if scenario_text:
        scenario_fit = _text_overlap(scenario_text, cluster.cluster_label)
        scenario_status = "scored"
    else:
        scenario_fit, scenario_status = 0.5, "neutral_unknown"

    level_text = str(preferences.get("target_level", {}).get("value", "")).strip()
    level_keywords = {
        "junior": ("初级", "应届", "实习", "junior"),
        "middle": ("中级", "middle"),
        "senior": ("高级", "资深", "专家", "senior", "负责人"),
    }
    target_levels = [
        code for code, words in level_keywords.items() if any(word in level_text for word in words)
    ]
    if target_levels and member_rows:
        member_levels = [level for _title, level in member_rows if level]
        if member_levels:
            level_fit = sum(1 for level in member_levels if level in target_levels) / len(
                member_levels
            )
            level_status = "scored"
        else:
            level_fit, level_status = 0.5, "neutral_unknown"
    else:
        level_fit, level_status = 0.5, "neutral_unknown"

    transferable = []
    gaps = []
    constraints_text = str(preferences.get("constraints", {}).get("value", "")).casefold()
    for metric in metrics:
        technology_id = metric["technology_node_id"]
        node = nodes.get(technology_id)
        technology_name = node.technology_name if node else ""
        if technology_id in profile_skill_ids:
            evidence = profile_skill_map[technology_id]
            if (
                technology_id in required_tech
                and float(metric["importance"]) >= 0.5
                and not _is_strong_evidence(evidence)
            ):
                gaps.append(
                    {
                        "technology_node_id": technology_id,
                        "gap_type_code": "depth_insufficient",
                        "importance_score": metric["importance"],
                        "candidate_evidence": [
                            f"skill:{evidence.candidate_skill_evidence_id}"
                        ],
                        "job_evidence": [
                            f"job:{code}" for code in metric["evidence_job_codes"][:10]
                        ],
                        "transfer_from_technology_node_id": None,
                        "explanation": GAP_EXPLANATIONS["depth_insufficient"],
                    }
                )
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
        explicit_missing = technology_id in confirmed_missing_ids or (
            technology_name and technology_name.casefold() in constraints_text
        )
        if explicit_missing:
            gap_type = "confirmed_missing"
        elif transfer_from:
            gap_type = "transferable"
            transferable.append(metric)
        else:
            requirement_confidence = tech_confidence.get(technology_id)
            gap_type = (
                "low_confidence_requirement"
                if requirement_confidence is not None and requirement_confidence < 0.6
                else "evidence_insufficient"
            )
        gaps.append(
            {
                "technology_node_id": technology_id,
                "gap_type_code": gap_type,
                "importance_score": metric["importance"],
                "candidate_evidence": ([f"technology:{transfer_from}"] if transfer_from else []),
                "job_evidence": [f"job:{code}" for code in metric["evidence_job_codes"][:10]],
                "transfer_from_technology_node_id": transfer_from,
                "explanation": GAP_EXPLANATIONS[gap_type],
            }
        )
    transfer_base = (
        sum(float(item["importance"]) for item in transferable) / req_total
        if req_total
        else 0.0
    )
    transfer_lower = min(1.0, transfer_base * 0.25)
    transfer_upper = min(1.0, transfer_base * 0.65)
    transfer_score = (transfer_lower + transfer_upper) / 2

    preference_fit = min(1.0, len(preferences) / len(QUESTION_BANK))
    preference_upper = 1.0 if preference_fit < 1.0 else 1.0
    values = {
        "required_capability_fit": (
            required_fit,
            required_lower,
            required_upper,
            "interval_scored",
        ),
        "bonus_capability_fit": (bonus_fit, bonus_lower, bonus_upper, bonus_status),
        "proficiency_fit": (
            proficiency_fit,
            proficiency_lower,
            proficiency_upper,
            "interval_scored",
        ),
        "task_semantic_fit": (
            task_fit,
            task_fit,
            task_fit,
            "scored" if profile_text else "neutral_unknown",
        ),
        "project_evidence_fit": (
            (project_lower + project_upper) / 2,
            project_lower,
            project_upper,
            "interval_scored",
        ),
        "recency_fit": (
            recency_fit,
            recency_lower,
            recency_upper,
            recency_status,
        ),
        "scenario_fit": (scenario_fit, scenario_fit, scenario_fit, scenario_status),
        "level_fit": (level_fit, level_fit, level_fit, level_status),
        "transferable_fit": (
            transfer_score,
            transfer_lower,
            transfer_upper,
            "interval_scored",
        ),
        "confirmed_preference_fit": (
            preference_fit,
            preference_fit,
            preference_upper,
            "interval_scored" if preference_fit < 1.0 else "scored",
        ),
    }
    dimensions = []
    weighted_sum = weighted_lower = weighted_upper = 0.0
    for code, label, weight in MATCH_DIMENSIONS:
        value, lower, upper, status = values[code]
        score = _round_score(value * 100)
        lower_score = _round_score(lower * 100)
        upper_score = _round_score(upper * 100)
        contribution = round(weight * score, 4)
        weighted_sum += contribution
        weighted_lower += weight * lower_score
        weighted_upper += weight * upper_score
        dimensions.append(
            {
                "code": code,
                "label": label,
                "score": score,
                "lower_score": lower_score,
                "upper_score": upper_score,
                "weight": weight,
                "contribution": contribution,
                "status": status,
            }
        )

    hard_failed_ids = (
        sorted(requirement_evaluation.failed_technology_ids)
        if requirement_evaluation is not None
        else sorted(
            technology_id
            for technology_id in required_tech & confirmed_missing_ids
            if tech_confidence.get(technology_id, 0.0) >= 0.6
        )
    )
    hard_constraints = {
        "enabled": True,
        "failed": bool(hard_failed_ids),
        "failed_technology_node_ids": hard_failed_ids,
        "score_cap": HARD_CONSTRAINT_SCORE_CAP if hard_failed_ids else None,
        "policy": "dsl_hard_requirement_cap",
        "requirement_expression": (
            requirement_expression.to_dict() if requirement_expression else None
        ),
        "proof": requirement_evaluation.proof if requirement_evaluation else None,
    }
    overall = _round_score(weighted_sum)
    lower_score = _round_score(weighted_lower)
    upper_score = _round_score(weighted_upper)
    if hard_failed_ids:
        overall = min(overall, HARD_CONSTRAINT_SCORE_CAP)
        lower_score = min(lower_score, HARD_CONSTRAINT_SCORE_CAP)
        upper_score = min(upper_score, HARD_CONSTRAINT_SCORE_CAP)

    acquisition_rounds = _evidence_acquisition_rounds(version, cluster.stable_cluster_code)
    if lower_score >= MATCH_DECISION_THRESHOLD:
        decision_status = "safe_match"
    elif upper_score < MATCH_DECISION_THRESHOLD:
        decision_status = "safe_nonmatch"
    elif acquisition_rounds >= MAX_EVIDENCE_ACQUISITION_ROUNDS:
        decision_status = "human_review"
    else:
        decision_status = "needs_evidence"
    score_interval = {
        "lower": lower_score,
        "point": overall,
        "upper": upper_score,
        "width": _round_score(upper_score - lower_score),
        "threshold": MATCH_DECISION_THRESHOLD,
        "semantics": "lower=已核验证据保守分；upper=未知项在规则允许范围内的乐观分",
    }
    score_projection = (
        ScoreProjection(
            fixed_lower=(weighted_lower - 0.34 * required_lower * 100.0) / 100.0,
            fixed_upper=(weighted_upper - 0.34 * required_upper * 100.0) / 100.0,
            requirement_weight=0.34,
            overall_threshold=MATCH_DECISION_THRESHOLD / 100.0,
            hard_score_cap=HARD_CONSTRAINT_SCORE_CAP / 100.0,
        )
        if requirement_expression is not None
        else None
    )
    evidence_questions = _build_evidence_questions(
        version=version,
        cluster=cluster,
        nodes=nodes,
        gaps=gaps,
        required_tech=required_tech,
        tech_confidence=tech_confidence,
        interval_width=score_interval["width"],
        requirement_expression=requirement_expression,
        requirement_context=requirement_context,
        score_projection=score_projection,
    )
    minimal_improvement_sets = []
    if requirement_expression is not None and requirement_context is not None:
        for plan in plan_minimal_improvement_sets(
            requirement_expression,
            requirement_context,
            score_projection=score_projection,
        ):
            payload = plan.to_dict()
            payload["technologies"] = [
                {
                    "technology_node_id": technology_id,
                    "technology_name": (
                        nodes[technology_id].technology_name
                        if technology_id in nodes
                        else None
                    ),
                }
                for technology_id in plan.technology_node_ids
            ]
            minimal_improvement_sets.append(payload)
    if decision_status == "needs_evidence" and not evidence_questions:
        decision_status = "human_review"
    next_question = evidence_questions[0] if decision_status == "needs_evidence" else None
    decision = {
        "status": decision_status,
        "threshold": MATCH_DECISION_THRESHOLD,
        "acquisition_rounds": acquisition_rounds,
        "maximum_acquisition_rounds": MAX_EVIDENCE_ACQUISITION_ROUNDS,
        "safe_stop": decision_status in {"safe_match", "safe_nonmatch"},
        "reason": _decision_reason(decision_status, lower_score, upper_score),
    }
    confidence = _round_score(max(5.0, min(95.0, 100.0 - score_interval["width"])))
    matched_names = [
        item["technology_name"]
        for item in metrics
        if item["technology_node_id"] in profile_skill_ids
    ][:3]
    reasons = [f"已有证据覆盖：{'、'.join(matched_names)}"] if matched_names else []
    reasons.append(
        f"确定性评分区间为[{lower_score:.1f}, {upper_score:.1f}]，决策状态为{decision_status}"
    )
    if transferable:
        reasons.append(f"存在{len(transferable)}项同能力域可迁移技术，但未按直接证据满分计入")
    if hard_failed_ids:
        reasons.append(f"{len(hard_failed_ids)}项高置信必备能力被明确否认，触发分数上限")
    return {
        "cluster": cluster,
        "overall_score": overall,
        "confidence_score": confidence,
        "dimensions": dimensions,
        "reasons": reasons,
        "gaps": sorted(gaps, key=lambda item: -float(item["importance_score"]))[:10],
        "decision": decision,
        "score_interval": score_interval,
        "hard_constraints": hard_constraints,
        "requirement_expression": (
            requirement_expression.to_dict() if requirement_expression else None
        ),
        "requirement_proof": (
            requirement_evaluation.proof if requirement_evaluation else None
        ),
        "acquisition_policy": {
            "selection_method": "one_step_expected_and_robust_voi",
            "decision_scope": "projected_overall_ten_dimension_score",
            "outcome_prior_source": "uncalibrated_default_v1",
            "llm_used_for_selection": False,
            "reference_date": reference_date.isoformat(),
            "improvement_set_method": "bounded_minimum_safe_acceptance_set",
            "requirement_source": (
                "human_confirmed_expression"
                if stored_requirement is not None
                else "compiled_flat_requirements"
            ),
            "requirement_expression_version": (
                stored_requirement.expression_version_no
                if stored_requirement is not None
                else None
            ),
        },
        "next_evidence_question": next_question,
        "evidence_question_candidates": evidence_questions[:3],
        "minimal_improvement_sets": minimal_improvement_sets,
    }


def _build_evidence_questions(
    *,
    version: CandidateProfileVersion,
    cluster: JobClusterVersion,
    nodes: dict[int, TechnologyNode],
    gaps: list[dict],
    required_tech: set[int],
    tech_confidence: dict[int, float],
    interval_width: float,
    requirement_expression: RequirementNode | None = None,
    requirement_context: RequirementContext | None = None,
    score_projection: ScoreProjection | None = None,
) -> list[dict]:
    """按决策价值选择问题；问题选择完全由机械事实和固定成本函数决定。"""
    history = list(
        ((version.fact_json or {}).get("evidence_acquisition") or {}).get("history") or []
    )
    asked_counts: dict[int, int] = defaultdict(int)
    for item in history:
        if item.get("cluster_code") != cluster.stable_cluster_code:
            continue
        try:
            asked_counts[int(item.get("technology_node_id"))] += 1
        except (TypeError, ValueError):
            continue
    gap_by_technology = {
        int(item["technology_node_id"]): item
        for item in gaps
        if item.get("technology_node_id") is not None
    }
    if requirement_expression is not None and requirement_context is not None:
        costs_by_technology = {}
        for technology_id in requirement_expression.technology_ids:
            gap = gap_by_technology.get(technology_id, {})
            gap_type = gap.get("gap_type_code", "evidence_insufficient")
            costs_by_technology[technology_id] = AcquisitionCosts(
                answer_cost=0.18 if gap_type == "depth_insufficient" else 0.14,
                privacy_risk=0.02,
                fairness_risk=0.03,
                manipulation_risk=0.16 if gap_type == "depth_insufficient" else 0.24,
                repetition_penalty=min(0.36, asked_counts[technology_id] * 0.12),
            )
        plans = plan_evidence_questions(
            requirement_expression,
            requirement_context,
            costs_by_technology=costs_by_technology,
            score_projection=score_projection,
        )
        questions = []
        for plan in plans:
            if plan.net_utility < EVIDENCE_QUESTION_VALUE_THRESHOLD:
                continue
            technology_id = plan.technology_node_id
            node = nodes.get(technology_id)
            if node is None:
                continue
            gap = gap_by_technology.get(technology_id, {})
            gap_type = gap.get("gap_type_code", "evidence_insufficient")
            plan_data = plan.to_dict()
            questions.append(
                {
                    "question_code": f"skill_evidence_{technology_id}",
                    "question_text": _evidence_question_text(
                        node.technology_name,
                        gap_type,
                    ),
                    "technology_node_id": technology_id,
                    "technology_name": node.technology_name,
                    "cluster_code": cluster.stable_cluster_code,
                    "gap_type_code": gap_type,
                    "decision_value": plan_data["net_utility"],
                    "value_components": {
                        "expected_value_of_information": plan_data[
                            "expected_value_of_information"
                        ],
                        "robust_value_of_information": plan_data[
                            "robust_value_of_information"
                        ],
                        "expected_interval_shrink": plan_data[
                            "expected_interval_shrink"
                        ],
                        "threshold_resolution_probability": plan_data[
                            "threshold_resolution_probability"
                        ],
                        **plan_data["costs"],
                    },
                    "outcome_simulations": plan_data["outcome_simulations"],
                    "selection_method": plan_data["selection_method"],
                    "decision_scope": "projected_overall_ten_dimension_score",
                    "outcome_prior_source": "uncalibrated_default_v1",
                }
            )
        return questions
    questions = []
    width_factor = min(1.0, max(0.0, interval_width / 100.0))
    for gap in gaps:
        gap_type = gap["gap_type_code"]
        if gap_type not in {
            "evidence_insufficient",
            "depth_insufficient",
            "transferable",
            "low_confidence_requirement",
        }:
            continue
        technology_id = int(gap["technology_node_id"])
        node = nodes.get(technology_id)
        if node is None:
            continue
        importance = min(1.0, max(0.1, float(gap["importance_score"])))
        required_factor = 1.0 if technology_id in required_tech else 0.65
        requirement_reliability = tech_confidence.get(technology_id, 0.7)
        answerability = 0.90
        answer_cost = 0.18 if gap_type == "depth_insufficient" else 0.14
        privacy_risk = 0.02
        fairness_risk = 0.03
        manipulation_risk = 0.16 if gap_type == "depth_insufficient" else 0.24
        repetition_penalty = min(0.36, asked_counts[technology_id] * 0.12)
        gross_value = (
            importance
            * required_factor
            * requirement_reliability
            * (0.55 + 0.45 * width_factor)
            * answerability
        )
        net_value = max(
            0.0,
            gross_value
            - 0.10 * answer_cost
            - 0.20 * privacy_risk
            - 0.10 * fairness_risk
            - 0.25 * manipulation_risk
            - repetition_penalty,
        )
        if net_value < EVIDENCE_QUESTION_VALUE_THRESHOLD:
            continue
        question_text = _evidence_question_text(node.technology_name, gap_type)
        questions.append(
            {
                "question_code": f"skill_evidence_{technology_id}",
                "question_text": question_text,
                "technology_node_id": technology_id,
                "technology_name": node.technology_name,
                "cluster_code": cluster.stable_cluster_code,
                "gap_type_code": gap_type,
                "decision_value": round(net_value, 6),
                "value_components": {
                    "gross_value": round(gross_value, 6),
                    "importance": round(importance, 6),
                    "required_factor": required_factor,
                    "requirement_reliability": round(requirement_reliability, 6),
                    "interval_width_factor": round(width_factor, 6),
                    "answer_cost": answer_cost,
                    "privacy_risk": privacy_risk,
                    "fairness_risk": fairness_risk,
                    "manipulation_risk": manipulation_risk,
                    "repetition_penalty": repetition_penalty,
                },
                "selection_method": "deterministic_decision_value",
            }
        )
    questions.sort(
        key=lambda item: (
            -float(item["decision_value"]),
            int(item["technology_node_id"]),
        )
    )
    return questions


def _evidence_question_text(technology_name: str, gap_type: str) -> str:
    if gap_type == "depth_insufficient":
        return (
            f"请补充一段能证明你实际使用“{technology_name}”的经历："
            "说明具体任务、你亲自采取的行动、时间以及可验证结果。"
        )
    if gap_type == "transferable":
        return (
            f"你已有相邻能力。是否直接使用过“{technology_name}”？"
            "如使用过，请说明项目任务、你的行动、时间和结果；如未使用过请明确说明。"
        )
    return (
        f"岗位对“{technology_name}”较关键，但当前材料没有充分证据。"
        "你是否实际使用过？请给出任务、个人行动、时间和可验证结果；没有使用过也请明确说明。"
    )


def _decision_reason(status: str, lower: float, upper: float) -> str:
    if status == "safe_match":
        return f"保守下界{lower:.2f}已达到阈值{MATCH_DECISION_THRESHOLD:.2f}"
    if status == "safe_nonmatch":
        return f"乐观上界{upper:.2f}仍低于阈值{MATCH_DECISION_THRESHOLD:.2f}"
    if status == "human_review":
        return "分数区间跨越阈值，但问题预算耗尽或没有足够高价值的合规问题"
    return f"分数区间[{lower:.2f}, {upper:.2f}]跨越阈值，需要补充高价值证据"


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


def _confirmed_missing_technology_ids(version: CandidateProfileVersion) -> set[int]:
    acquisition = ((version.fact_json or {}).get("evidence_acquisition") or {})
    result: set[int] = set()
    for item in acquisition.get("confirmed_missing_technology_ids", []):
        try:
            result.add(int(item))
        except (TypeError, ValueError):
            continue
    return result


def _evidence_acquisition_rounds(
    version: CandidateProfileVersion, cluster_code: str
) -> int:
    history = list(
        ((version.fact_json or {}).get("evidence_acquisition") or {}).get("history") or []
    )
    return sum(1 for item in history if item.get("cluster_code") == cluster_code)


def _classify_evidence_answer(answer: str) -> str:
    """机械分类补证回答；不让 LLM 把自我声明升级为已验证事实。"""
    normalized = re.sub(r"\s+", "", answer.casefold())
    negative_markers = (
        "不会",
        "不具备",
        "不了解",
        "未使用过",
        "没有使用过",
        "没用过",
        "没做过",
        "无相关经验",
        "notused",
        "noexperience",
    )
    context_markers = (
        "项目",
        "负责",
        "实现",
        "开发",
        "部署",
        "优化",
        "验证",
        "指标",
        "结果",
        "上线",
        "故障",
        "代码",
        "实验",
        "年",
        "月",
    )
    has_negative = any(marker in normalized for marker in negative_markers)
    context_hits = sum(1 for marker in context_markers if marker in normalized)
    positive_action_markers = (
        "负责",
        "实现",
        "开发",
        "部署",
        "优化",
        "验证",
        "上线",
        "编写",
        "完成",
    )
    if has_negative and not any(marker in normalized for marker in positive_action_markers):
        return "confirmed_missing"
    if len(answer.strip()) >= 20 and context_hits >= 2:
        return "contextual"
    return "self_claim"


def _evidence_state_label(state: str) -> str:
    return {
        "verified": "可验证证据",
        "contextual": "情境化证据",
        "self_claim": "自我声明",
        "contradicted": "矛盾证据",
        "confirmed_missing": "明确缺失事实",
    }.get(state, state)


def _get_match_result(db: Session, result_code: str) -> CandidateMatchResult:
    result = db.scalar(
        select(CandidateMatchResult).where(
            CandidateMatchResult.result_code == result_code
        )
    )
    if result is None:
        raise TalentWorkflowError("匹配结果不存在")
    return result


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
