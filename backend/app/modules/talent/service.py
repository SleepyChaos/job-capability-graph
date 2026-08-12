import hashlib
import json
import re
from collections import defaultdict
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
from app.modules.job.models import JobPosting, JobRequirement
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
    ResumeDocument,
)
from app.modules.taxonomy.models import TechnologyAlias, TechnologyNode

PROFILE_PARSER_VERSION = "candidate_profile_rules_v1"
MATCH_ALGORITHM_VERSION = "evidence_match_p1_v1"
PATH_ALGORITHM_VERSION = "gap_path_topo_v1"
MIN_DIALOGUE_ROUNDS = 2
MAX_DIALOGUE_ROUNDS = 8
QUESTION_VALUE_THRESHOLD = 0.05

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


def run_matching(db: Session, *, version_code: str, limit: int = 5) -> dict:
    version = _get_version(db, version_code)
    if version.workflow_status_code != "confirmed":
        raise TalentWorkflowError("只有已确认画像可以发起岗位匹配")
    context = _context(db)
    profile_skills = _skills(db, version.candidate_profile_version_id)
    profile_skill_map = {item.technology_node_id: item for item in profile_skills}
    profile_skill_ids = set(profile_skill_map)
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
                    explanation_json=dimension.get("explanation"),
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
    return (
        f"综合匹配分 {float(result.overall_score):.1f}，主要贡献维度：{top_labels}。{gap_summary}"
        "缺失证据不等于不会，补充项目证据后可重算。"
    )


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


def _skill_strength(evidence: CandidateSkillEvidence) -> float:
    if evidence.user_confirmed:
        return 1.0
    confidence = float(evidence.confidence_score)
    if confidence >= 90:
        return 0.9
    if confidence >= 80:
        return 0.75
    return 0.6


def _is_strong_evidence(evidence: CandidateSkillEvidence) -> bool:
    return (
        evidence.user_confirmed
        or float(evidence.confidence_score) >= 90
        or len(evidence.evidence_text or "") >= 120
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


def _score_cluster(
    db: Session,
    nodes: dict[int, TechnologyNode],
    version: CandidateProfileVersion,
    cluster: JobClusterVersion,
    metrics: list[dict],
    member_ids: set[int],
    profile_skill_map: dict[int, CandidateSkillEvidence],
) -> dict:
    profile_skill_ids = set(profile_skill_map)
    preferences = version.preference_json or {}
    required_tech, bonus_tech, tech_confidence = _cluster_requirement_profile(
        db, nodes, member_ids
    )

    # 1) 必需能力覆盖：无必需技术要求时回退为全部重要能力
    req_metrics = [item for item in metrics if item["technology_node_id"] in required_tech]
    if not req_metrics:
        req_metrics = metrics
    req_total = sum(max(item["importance"], 1) for item in req_metrics)
    req_hit = sum(
        item["importance"]
        for item in req_metrics
        if item["technology_node_id"] in profile_skill_ids
    )
    required_fit = req_hit / req_total if req_total else 0.0

    # 2) 加分能力覆盖（无加分项时为中性 unknown，不奖不罚）
    bonus_metrics = [item for item in metrics if item["technology_node_id"] in bonus_tech]
    if bonus_metrics:
        bonus_total = sum(max(item["importance"], 0.5) for item in bonus_metrics)
        bonus_hit = sum(
            item["importance"]
            for item in bonus_metrics
            if item["technology_node_id"] in profile_skill_ids
        )
        bonus_fit, bonus_status = bonus_hit / bonus_total, "scored"
    else:
        bonus_fit, bonus_status = 0.5, "neutral_unknown"

    matched_evidence = [
        profile_skill_map[item["technology_node_id"]]
        for item in metrics
        if item["technology_node_id"] in profile_skill_ids
    ]

    # 3) 技能深度与熟练度：命中能力的证据强度均值
    proficiency_fit = (
        sum(_skill_strength(item) for item in matched_evidence) / len(matched_evidence)
        if matched_evidence
        else 0.0
    )

    # 4) 任务语义：求职目标与经历摘要 vs 岗位簇标签和成员 JD 标题
    member_rows = db.execute(
        select(JobPosting.job_title_normalized, JobPosting.job_level_code).where(
            JobPosting.job_posting_id.in_(member_ids or {-1})
        )
    ).all()
    profile_text = " ".join(
        part for part in [version.target_role_text, version.experience_summary] if part
    )
    title_texts = [title for title, _level in member_rows[:8] if title]
    task_fit = _text_overlap(profile_text, cluster.cluster_label) if profile_text else 0.0
    if profile_text and title_texts:
        task_fit = max(task_fit, _text_overlap(profile_text, " ".join(title_texts)))

    # 5) 项目证据：命中能力中强证据（用户确认/长上下文/补充来源）占比
    strong_evidence = [item for item in matched_evidence if _is_strong_evidence(item)]
    project_fit = len(strong_evidence) / len(matched_evidence) if matched_evidence else 0.0

    # 6) 时间新鲜度：P0 简历无技能使用时间，按中性 unknown 处理，不视为负面
    recency_fit, recency_status = 0.5, "neutral_unknown"

    # 7) 行业与场景：用户确认的目标场景与岗位簇标签比较
    scenario_text = str(preferences.get("target_scenario", {}).get("value", "")).strip()
    if scenario_text:
        scenario_fit = _text_overlap(scenario_text, cluster.cluster_label)
        scenario_status = "scored"
    else:
        scenario_fit, scenario_status = 0.5, "neutral_unknown"

    # 8) 岗位级别：目标级别关键词与成员 JD 级别分布比较
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

    # 9) 可迁移能力：同 L2 相邻技术的重要度占比
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
                and metric["importance"] >= 0.5
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
        if technology_name and technology_name.casefold() in constraints_text:
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
    transfer_score = (
        sum(item["importance"] for item in transferable) / req_total if req_total else 0
    )

    # 10) 已确认职业意向：已回答追问占比
    preference_fit = min(1.0, len(preferences) / len(QUESTION_BANK))

    hard_constraint_penalty = 0.0
    values = {
        "required_capability_fit": (required_fit, "scored"),
        "bonus_capability_fit": (bonus_fit, bonus_status),
        "proficiency_fit": (proficiency_fit, "scored"),
        "task_semantic_fit": (task_fit, "scored" if profile_text else "neutral_unknown"),
        "project_evidence_fit": (project_fit, "scored"),
        "recency_fit": (recency_fit, recency_status),
        "scenario_fit": (scenario_fit, scenario_status),
        "level_fit": (level_fit, level_status),
        "transferable_fit": (min(transfer_score, 1.0), "scored"),
        "confirmed_preference_fit": (preference_fit, "scored"),
    }
    dimensions = []
    weighted_sum = 0.0
    for code, label, weight in MATCH_DIMENSIONS:
        value, status = values[code]
        score = _round_score(value * 100)
        contribution = round(weight * score, 4)
        weighted_sum += contribution
        dimensions.append(
            {
                "code": code,
                "label": label,
                "score": score,
                "weight": weight,
                "contribution": contribution,
                "status": status,
            }
        )
    overall = _round_score(weighted_sum - hard_constraint_penalty)
    confidence = _round_score(
        min(92, 55 + len(profile_skill_ids) * 2 + min(cluster.member_count, 20))
    )
    matched_names = [
        item["technology_name"]
        for item in metrics
        if item["technology_node_id"] in profile_skill_ids
    ][:3]
    reasons = [f"已有证据覆盖：{'、'.join(matched_names)}"] if matched_names else []
    if transferable:
        reasons.append(f"存在{len(transferable)}项同能力域可迁移技术")
    neutral_count = sum(1 for item in dimensions if item["status"] == "neutral_unknown")
    if neutral_count:
        reasons.append(f"{neutral_count}个维度因缺少画像或时间数据按中性处理，未计为负面")
    if not reasons:
        reasons.append("当前主要依据求职目标和有限技术证据召回，需补充项目证据")
    return {
        "cluster": cluster,
        "overall_score": overall,
        "confidence_score": confidence,
        "dimensions": dimensions,
        "reasons": reasons,
        "gaps": sorted(gaps, key=lambda item: -item["importance_score"])[:10],
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
