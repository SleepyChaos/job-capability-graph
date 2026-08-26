import hashlib
import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

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
    estimate_transmission_lag,
    score_candidate,
)
from app.modules.discovery.foresight import (
    JOBIFICATION_THRESHOLD,
    TRANSMISSION_LAG_PRIOR_MONTHS,
    DatedEvent,
    ForesightResult,
    compute_foresight,
    horizon_label,
    rank_foresight,
)
from app.modules.discovery.itemsets import (
    ITEMSET_ALGORITHM_VERSION,
    assign_transactions,
    mine_closed_itemsets,
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

# v1_6：候选粒度由技术对改为频繁闭项集（技术组合）。
# v1_7：候选排序改为「JD 数 × 组合大小」（纯按支持度排会让名额被最小组合占满），
#       且与既有岗位的重合度改按技术编码比较（节点 id 逐词表版本独立，跨版本恒为空集）。
# v1_8：里程碑技术链接同样按技术编码重映射到本次词表版本。此前链接停留在 v1.1 节点上，
#       换到 v1.2 后成熟度对所有节点恒为 0，成熟度维度与 emerging 门控实际上是失效的。
# v1_9：候选在核心组合之外补一层画像（支撑 JD 中过半出现的技术），供 JD 生成与展示；
#       核心层仍单独保留，身份、去重键与覆盖率测量不变。同时把支撑 JD 数下沉为列。
logger = logging.getLogger(__name__)

ALGORITHM_VERSION = "evidence_gap_discovery_v1_15"

# **缺口分析两条路径的版本号也放在这里。** 它们由 `tools/build_*_candidates.py`
# 写入运行记录，而图谱要靠版本号判断候选是否为当前版本产物。此前版本号散在工具
# 里、图谱侧另抄一份字符串，抄错一个字（`upstream_gap_v1` 之于
# `upstream_gap_candidate_v1`）就会让那一整类候选静默地从图谱上消失，且不报错。
UPSTREAM_GAP_ALGORITHM_VERSION = "upstream_gap_candidate_v1"
MILESTONE_GAP_ALGORITHM_VERSION = "milestone_gap_v1"

#: 证据来自招聘语料之外的候选分类。它们的评分量纲与主路径不可比。
EXTERNAL_EVIDENCE_CLASSIFICATIONS = frozenset({"upstream_signal", "milestone_signal"})
# 覆盖率分档阈值。与 tools/experiment_measure_ablation.py 保持同一口径。
EXISTING_ROLE_COVERAGE = 0.75
ROLE_EVOLUTION_COVERAGE = 0.45
# 候选至少要占到最近岗位能力集的这个比例，才算「就是那个岗位」而不是它的一个片段。
# 候选被完全包含时 Jaccard 恰等于 |候选| / |岗位|，所以这个阈值可直接读作规模占比。
ROLE_SCOPE_JACCARD = 0.5

# 已成为正式岗位、已并入既有岗位或已被驳回的候选不再重复提出。
TERMINAL_CANDIDATE_STATUSES = frozenset({"approved", "merged", "rejected"})
DEFAULT_PARAMETERS = {
    # 候选组合的支持度下限（按 JD 条数计）与大小区间。
    # 候选粒度从技术对提到技术组合后，覆盖率 |候选∩岗位|/|候选| 的分母不再恒为 2，
    # classification_code 的 0.45/0.75 两个阈值才有分档能力。
    "min_pair_job_count": 2,
    "min_combination_size": 2,
    "max_combination_size": 5,
    "max_communities": 100,
    "exploration_floor": 0.15,
    # 里程碑挂在 L1/L2，而 JD 证据和候选都在 L3。没有直接证据的节点沿父链继承祖先证据，
    # 每上溯一层按该系数折减相关度，保证有直接证据的节点始终排在继承者前面。
    "maturity_alpha": 0.17,
    "ancestor_inheritance_decay": 0.6,
    # 技术词少于该数量的岗位版本不足以构成可比的岗位定义，不参与最近岗位比较。
    "min_role_technology_count": 2,
    # 反事实分析用：把这些岗位当作不存在（留出重发现实验）。
    "excluded_role_ids": [],
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
    # 支撑 JD 中各技术点出现的 JD 数。核心组合只有 2–5 个技术，撑不起一份标准化 JD；
    # 由它扩展出的「画像层」用这个计数按过半规则筛选。
    technology_counts: Counter[int] = field(default_factory=Counter)


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
        refreshed_count = 0
        skipped_count = 0
        if mode_code == "name_inference":
            candidate_count, task_count = _run_name_inference(db, run)
        else:
            (
                candidate_count,
                task_count,
                refreshed_count,
                skipped_count,
            ) = _run_evidence_discovery(db, run, selected_ids, config)
        verified_milestones = int(snapshot["verified_milestone_count"])
        approved_roles = int(snapshot["approved_role_count"])
        evidence_limited = verified_milestones == 0 or approved_roles == 0
        run.result_summary_json = {
            "candidate_count": candidate_count,
            "refreshed_candidate_count": refreshed_count,
            "skipped_settled_candidate_count": skipped_count,
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


EXPRESSION_PROMPT_VERSION = "candidate_expression_v5_fields_are_about_the_role"


def auto_candidate_expression(db: Session, *, candidate_code: str) -> EmergingRoleCandidate:
    """一键生成表达层：LLM 可用时生成并校验，否则规则降级（设计 §8.5、§12.3）。"""
    candidate = db.scalar(
        select(EmergingRoleCandidate).where(EmergingRoleCandidate.candidate_code == candidate_code)
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


# 模型给岗位命名时最容易攀附的域外应用领域。这些词在本词表里没有对应技术点
# （或只作为某个 L4 词的一部分出现），一旦进入名称就是对岗位应用域的臆断——
# 实测 8 个候选里有 2 个被命名为「自动驾驶大模型训练优化工程师」，而其技术组合
# 只有 VLA 端到端大模型与大模型推理服务，没有任何自动驾驶相关证据。
OUT_OF_SCOPE_DOMAIN_TERMS = (
    "自动驾驶", "智能驾驶", "无人驾驶", "车载", "汽车",
    "医疗", "医学", "金融", "风控", "安防", "军工", "游戏",
)


def _name_asserts_unsupported_domain(name: str, allowed_terms: set[str]) -> str | None:
    """名称是否声称了候选技术支撑不了的应用域，返回越界的词。

    表达层允许改写措辞，**不允许新增事实**。岗位的应用域属于事实：说一个岗位是
    「自动驾驶」岗，是在断言它服务于某个技术组合里并不存在的场景。这类越界不会被
    JSON 结构校验拦住，因此单独检查。

    `allowed_terms` 是候选自身技术名与其祖先名的并集——若某个域确实来自候选的技术，
    它出现在名称里就是有据的，不算越界。
    """
    for term in OUT_OF_SCOPE_DOMAIN_TERMS:
        if term in name and not any(term in allowed for allowed in allowed_terms):
            return term
    return None


def _llm_expression(card: dict, candidate, technologies: list[dict]) -> dict | None:
    from app.infrastructure.llm import generate, validate_schema

    task_source = card.get("task_text_source") or "unknown"
    # 逐字段标注可靠度：机械层的任务文本取自 JD 职责抽取，存在切分错误与
    # 招聘平台样板文字的残留风险；数值类事实由确定性算法产出，可靠。
    facts = {
        # **不叫 proposed_name。** 机械名是把技术名拼起来的占位符，不是事实；
        # 以 proposed_name 的名义传进去，模型会依据「只能使用给定机械事实」这条
        # 硬约束原样抄回来——实测 6 个候选无一例外，LLM 命名等于没做。
        "placeholder_name_to_replace": candidate.proposed_name,
        "technologies": [
            {"name": item["technology_name"], "requirement_type": item["requirement_type"]}
            for item in technologies[:12]
        ],
        "evidence": {
            "job_count": card.get("job_count"),
            "organization_count": card.get("organization_count"),
            "source_count": card.get("source_count"),
            "observation_window_count": card.get("observation_window_count"),
            "task_gap": card.get("task_gap"),
            "maturity_raw": card.get("maturity_raw"),
            "nearest_role_overlap": card.get("nearest_role_overlap"),
        },
        "representative_task_text": card.get("task_text"),
        # 最邻近的既有岗位。没有它，「与既有岗位的差异」这一字段无从写起——
        # 此前只给了一个覆盖率数字，模型没有可比的对象，只能去谈命名本身。
        "nearest_existing_role": card.get("nearest_role"),
        "field_reliability": {
            "technologies": "high",
            "evidence": "high",
            "representative_task_text": (
                "high" if task_source == "jd_responsibility" else "low_fallback_placeholder"
            ),
        },
    }
    system_prompt = (
        "你是岗位研究助手，只做表达层改写。\n"
        "命名任务：\n"
        "placeholder_name_to_replace 是把技术名拼接而成的占位符，**不是岗位名，"
        "必须替换**。请依据技术组合与代表性职责，给出一个中文招聘市场上真实会出现的"
        "职位名称——像 JD 标题那样，通常 6–14 字，体现岗位的职责定位而非技术清单；"
        "不要用顿号或「与」把多个技术并列起来充当名称。\n"
        "硬约束：\n"
        "1. 只能使用给定机械事实，不得新增技术、数字或技能。"
        "命名可以概括这些技术所属的职责方向，但不得引入事实中没有的技术。\n"
        "2. **不得在名称里声称应用领域**（自动驾驶、车载、医疗、金融、安防等），"
        "除非该领域确实出现在给定技术中。岗位服务于哪个场景属于事实，不是措辞。\n"
        "3. field_reliability 标为 low 的字段可能来自抽取错误："
        "只允许忽略该字段，禁止用推测内容替换它，也不得据此编造替代事实。\n"
        "4. representative_task_text 是原始 JD 职责摘录，可能含切分错误或残缺句；"
        "可提炼其语义，但不得把其中出现的公司名、平台名当作岗位职责。\n"
        "5. 若可用事实不足以支撑某个字段，写明证据不足，不要编造。\n"
        "输出 JSON，五个键的含义如下，**都在写这个岗位本身，不要写你的命名过程**：\n"
        "- proposed_name：岗位名称，见上文命名任务。\n"
        "- one_line_definition：一句话说明这个岗位做什么。\n"
        "- core_responsibilities：核心职责数组，从代表性职责与技术组合提炼。\n"
        "- formation_reason：**这个岗位为什么会在市场上形成**。依据证据事实作答——"
        "多少家企业在招、多少份 JD 支撑、这组技术为什么会被同一个职位同时要求。"
        "不要解释名称是怎么取的。\n"
        "- difference_explanation：**与 nearest_existing_role 给出的那个既有岗位"
        "相比，这个岗位差在哪**。围绕职责范围与能力构成作答，可引用其名称与共有/"
        "独有的能力数量。若 nearest_existing_role 为空，写明没有可比的既有岗位。"
        "不要比较名称的写法。"
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
    # 名称越界视同事实被改写，整条结果作废走规则降级——保留一个措辞更差但有据的名字，
    # 好过一个读起来专业却断言了错误应用域的名字。
    allowed_terms = {item["technology_name"] for item in technologies}
    allowed_terms.update(str(card.get("task_text") or ""))
    violation = _name_asserts_unsupported_domain(str(data["proposed_name"]), allowed_terms)
    if violation is not None:
        logger.warning(
            "候选 %s 的 LLM 命名声称了技术组合不支撑的应用域「%s」，降级为规则表达",
            candidate.candidate_code,
            violation,
        )
        return None
    data["_model"] = result.model
    return data


def _rule_expression(card: dict, candidate, technologies: list[dict]) -> dict:
    required_names = [
        item["technology_name"] for item in technologies if item["requirement_type"] == "required"
    ][:5]
    bonus_names = [
        item["technology_name"] for item in technologies if item["requirement_type"] != "required"
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
) -> tuple[int, int, int, int]:
    """返回 (新建候选, 任务, 刷新候选, 因已处置而跳过)。"""
    min_role_technology_count = int(parameters.get("min_role_technology_count", 2))
    excluded_role_ids = frozenset(int(item) for item in parameters.get("excluded_role_ids") or [])
    ancestors = _ancestor_chains(db, run.taxonomy_version_id)
    parse_run_id = db.scalar(
        select(JobClusteringRun.job_parse_run_id).where(
            JobClusteringRun.clustering_run_id == run.clustering_run_id
        )
    )
    maturity = _persist_maturity(db, run, selected_ids, parameters, ancestors)
    foresight = _l2_foresight(db, run)
    technology_frequency = _technology_job_frequency(db, run, parse_run_id)
    job_demand = _l2_job_demand(db, parse_run_id)
    pair_evidence = _collect_pair_evidence(db, run, selected_ids, parse_run_id, parameters)
    ranked = _rank_candidate_combinations(pair_evidence, parameters)
    candidate_count = 0
    refreshed_count = 0
    skipped_count = 0
    task_count = 0
    # **不按词表版本过滤。** 技术 id 来自解析运行所用的版本，而推演运行取的是当前
    # 最新的活跃版本——词表一升级两者就会错开，按版本过滤会直接 KeyError。
    # 节点 id 全局唯一，全量映射既正确又不受版本错配影响。
    # （这是节点 id 被当作跨版本标识符使用的第七处，前六处见 _nearest_role、
    # _candidate_key、_milestone_signals_by_node、_candidate_projection 与两个实验脚本。）
    code_by_node = {
        node_id: code
        for node_id, code in db.execute(
            select(TechnologyNode.technology_node_id, TechnologyNode.technology_code)
        )
    }
    for technology_ids, evidence in ranked:
        if len(evidence.job_ids) < int(parameters["min_pair_job_count"]):
            continue
        candidate_key = _candidate_key(
            run.mode_code, tuple(code_by_node[item] for item in technology_ids)
        )
        existing = db.scalar(
            select(EmergingRoleCandidate).where(
                EmergingRoleCandidate.candidate_key == candidate_key
            )
        )
        if existing is not None and existing.workflow_status_code in TERMINAL_CANDIDATE_STATUSES:
            # 已处置过的技术组合不再重复提出，也不必再落任务和社区。
            skipped_count += 1
            continue
        task = _persist_task(
            db,
            run,
            technology_ids,
            evidence,
            maturity,
            ancestors,
            min_role_technology_count,
            excluded_role_ids,
        )
        task_count += 1
        community = TaskCommunity(
            discovery_run_id=run.discovery_run_id,
            community_code=f"community_{_stable_digest(technology_ids)[:16]}",
            community_label=task.task_name,
            grouping_method_code="technology_cooccurrence_fallback",
            cohesion_score=Decimal(
                str(
                    round(
                        _combination_cohesion(
                            technology_ids, len(evidence.job_ids), technology_frequency
                        ),
                        6,
                    )
                )
            ),
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
        reused = _persist_candidate(
            db,
            run,
            community,
            task,
            technology_ids,
            evidence,
            maturity,
            ancestors,
            foresight,
            technology_frequency,
            job_demand,
            candidate_key=candidate_key,
            min_role_technology_count=min_role_technology_count,
            excluded_role_ids=excluded_role_ids,
            existing=existing,
        )
        if reused:
            refreshed_count += 1
        else:
            candidate_count += 1
    return candidate_count, task_count, refreshed_count, skipped_count


def _technology_job_frequency(
    db: Session, run: DiscoveryRun, parse_run_id: int
) -> dict[int, int]:
    """每个技术点在整个语料里被多少份 JD 提及，作为内聚度的分母。"""
    rows = db.execute(
        select(
            JobRequirement.technology_node_id,
            func.count(func.distinct(JobRequirement.job_posting_id)),
        )
        .join(
            TechnologyMatchAssessment,
            TechnologyMatchAssessment.job_requirement_id == JobRequirement.job_requirement_id,
        )
        .where(
            TechnologyMatchAssessment.job_parse_run_id == parse_run_id,
            TechnologyMatchAssessment.assessment_status_code == "accepted",
            JobRequirement.technology_node_id.is_not(None),
        )
        .group_by(JobRequirement.technology_node_id)
    ).all()
    return {node_id: int(count) for node_id, count in rows}


def _combination_cohesion(
    technology_ids: tuple[int, ...], support: int, frequency: dict[int, int]
) -> float:
    """技术组合的内聚度：组合的支撑量占其中最常见技术单独出现量的比例。

    问的是「这些技术真的成套出现，还是只是搭上了一个高频技术的顺风车」。
    强化学习出现在 400 份 JD 里、某组合出现在 30 份里，那这个组合对强化学习而言
    是偶然的（内聚度 0.075）；若某技术只出现在 35 份 JD 里而组合占了 30 份，
    它们基本总是同时出现（内聚度 0.857）。

    **此前这一维是常量**：写死为「单技术 1.0，其余 0.75」，227 个候选里 214 个
    取到同一个值，对排序完全不产生区分度。分母取最常见的那个技术是保守选择——
    它给出组合内聚度的下界，不会因为组合里混进一个冷门技术而虚高。
    """
    if not technology_ids or support <= 0:
        return 0.0
    ceiling = max(frequency.get(item, 0) for item in technology_ids)
    if ceiling <= 0:
        return 0.0
    return min(1.0, support / ceiling)


def _evidence_completeness(
    *,
    evidence: "_PairEvidence",
    application_count: int,
    has_real_responsibility: bool,
    milestone_backed: bool,
) -> float:
    """证据**齐备度**：五类证据里齐了几类，而不是某一类攒了多少条。

    此前按 `min(1.0, 证据 JD 数 / 5)` 计算，而候选的支撑 JD 普遍在 30–60 份，
    这一维因此恒为 1.0，227 个候选无一例外，对排序不产生任何区分度。
    数量已经由 market_support 表达，这里改测**广度**：缺哪一类证据是可读的信息，
    正好与合取门控的风险旗标相呼应。
    """
    checks = (
        len(evidence.evidence_job_ids) >= 5,
        len(evidence.organization_ids) >= 2,
        len(evidence.source_ids) >= 2,
        application_count >= 1,
        has_real_responsibility and milestone_backed,
    )
    return sum(1 for item in checks if item) / len(checks)


# 技术名里 471 个 L3 有 110 个自带「与」，用「与」拼接会让边界消失——
# 「推理引擎与端侧部署与GPU并行计算与算子优化工程师」实际只是两个技术名拼起来的。
# 「·」在全部 L3 技术名中零出现，是唯一安全的连接符。
MECHANICAL_NAME_SEPARATOR = "·"


def _mechanical_name(technology_names: list[str]) -> str:
    """候选的机械名。

    **这是占位名，不是岗位名。** 它的职责是唯一且可追溯，不是好看——真正的命名由
    表达层的 LLM 完成（`auto_candidate_expression`），机械名只在 LLM 不可用时兜底。

    此前取 `"与".join(names[:2])`，两个缺陷叠在一起：丢掉第三个及以后的技术，
    使不同的技术组合拼出同一个名字（227 个候选只有 142 个不同名称，46 组重名）；
    又用了技术名内部高频出现的「与」当连接符，读者无法判断边界在哪。
    这里保留全部技术并改用零冲突的分隔符，名字会变长，但长本身就是「此候选尚未
    命名」的信号。
    """
    if not technology_names:
        return "未命名候选岗位"
    return MECHANICAL_NAME_SEPARATOR.join(technology_names) + "工程师"


def _rank_candidate_combinations(
    evidence: dict[tuple[int, ...], _PairEvidence], parameters: dict
) -> list[tuple[tuple[int, ...], _PairEvidence]]:
    """给候选组合排序并截断到本次推演的名额。

    **不能单纯按支持度排。** 项集的支持度沿子集单调不减，纯按 JD 数排序会让名额
    几乎全被最小的组合占满——实测 100 个名额里 82 个是二元组，粒度提升等于没做。
    这里按「覆盖的 JD 数 × 组合大小」排序：它同时奖励证据充足与能力集完整，
    量纲上等价于该组合在语料中支撑的「技术-岗位」证据格点数。

    同分时按技术 id 元组升序，保证可重放。
    """
    max_communities = int(parameters["max_communities"])
    ranked = sorted(
        evidence.items(),
        key=lambda item: (-(len(item[1].job_ids) * len(item[0])), item[0]),
    )
    return ranked[:max_communities]


def _collect_pair_evidence(
    db: Session,
    run: DiscoveryRun,
    selected_ids: list[int],
    parse_run_id: int,
    parameters: dict | None = None,
) -> dict[tuple[int, ...], _PairEvidence]:
    """证据必须与本次推演绑定的聚类运行同源。

    JD 更新后会产生新的解析运行，若不锁定解析运行，推演就会把多代解析的评估
    混在一起：聚类结构来自上一代、技术证据来自新一代，两者口径不一致，且证据
    片段会随解析次数累积虚高。
    """
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
            TechnologyMatchAssessment.job_parse_run_id == parse_run_id,
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
        select(JobResponsibility).where(
            JobResponsibility.job_posting_id.in_(list(jobs) or [-1]),
            JobResponsibility.job_parse_run_id == parse_run_id,
        )
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
    keys_by_job = _candidate_keys_by_job(jobs, selected, selected_ids, parameters or {})
    for job_id, (posting, technology_ids, evidence_ids) in jobs.items():
        if selected and not selected.issubset(technology_ids):
            continue
        keys = keys_by_job.get(job_id, ())
        for key in keys:
            bucket = result.setdefault(key, _PairEvidence(set(), set(), set(), set(), [], {}))
            bucket.job_ids.add(job_id)
            bucket.technology_counts.update(technology_ids)
            if posting.organization_id:
                bucket.organization_ids.add(posting.organization_id)
            bucket.source_ids.update(sources[job_id] or {posting.data_source_id})
            if posting.source_collected_at:
                bucket.observation_windows.add(posting.source_collected_at.strftime("%Y-%m"))
            bucket.responsibilities.extend(responsibilities[job_id])
            bucket.evidence_job_ids.update({evidence_id: job_id for evidence_id in evidence_ids})
    return result


def _candidate_keys_by_job(
    jobs: dict[int, tuple[JobPosting, set[int], set[int]]],
    selected: set[int],
    selected_ids: list[int],
    parameters: dict,
) -> dict[int, tuple[tuple[int, ...], ...]]:
    """决定每份 JD 的技术证据挂到哪些候选键上。

    技术定向模式下键就是用户选定的组合，无须挖掘。自动模式下用频繁闭项集把候选
    从「任意两个技术的共现」提到「反复共现的能力集合」——这是覆盖率测量能有分辨率
    的前提（见 `discovery/itemsets.py` 的说明）。
    """
    if selected:
        return {job_id: (tuple(selected_ids),) for job_id in jobs}

    transactions = {job_id: set(technology_ids) for job_id, (_, technology_ids, _) in jobs.items()}
    mined = mine_closed_itemsets(
        transactions,
        min_support=max(1, int(parameters.get("min_pair_job_count", 2))),
        min_size=int(parameters.get("min_combination_size", 2)),
        max_size=int(parameters.get("max_combination_size", 5)),
    )
    assigned = assign_transactions(
        transactions, mined.itemsets, min_size=int(parameters.get("min_combination_size", 2))
    )
    keys_by_job: dict[int, list[tuple[int, ...]]] = defaultdict(list)
    for key, job_ids in assigned.items():
        for job_id in job_ids:
            keys_by_job[job_id].append(key)
    return {job_id: tuple(sorted(keys)) for job_id, keys in keys_by_job.items()}


def _ancestor_chains(db: Session, taxonomy_version_id: int) -> dict[int, tuple[int, ...]]:
    """返回每个技术节点由近及远的祖先链，用于成熟度证据上溯。"""
    parents = {
        node_id: parent_id
        for node_id, parent_id in db.execute(
            select(
                TechnologyNode.technology_node_id, TechnologyNode.parent_technology_node_id
            ).where(
                TechnologyNode.taxonomy_version_id == taxonomy_version_id,
                TechnologyNode.governance_status_code == "active",
            )
        )
    }
    chains: dict[int, tuple[int, ...]] = {}
    for node_id in parents:
        chain = []
        current = parents.get(node_id)
        while current is not None and current in parents and current not in chain:
            chain.append(current)
            current = parents.get(current)
        chains[node_id] = tuple(chain)
    return chains


def l2_dated_events(db: Session) -> dict[str, list[DatedEvent]]:
    """按 L2 归集带真实日期的已核实里程碑，供前瞻计算使用。

    与 `_milestone_signals_by_node` 的区别有两处：这里保留**绝对日期**（成熟度
    轨迹要在任意 as-of 时点重算年龄），并且是**向上汇总**——挂在 L3 上的突破
    同样算作其所属 L2 方向的证据，不做继承衰减。`_inherited_signals` 做的是
    反方向的事（L3 自身没有证据时向上借），两者不冲突。

    归集到 L2 而非 L3，是因为 L3 的成熟度取值重复率 84.3%：绝大多数 L3 没有
    自己的里程碑，同一 L2 下的 L3 会拿到完全相同的成熟度，在这样的取值上排序
    会大面积并列。
    """
    linked = aliased(TechnologyNode)
    parent = aliased(TechnologyNode)
    rows = db.execute(
        select(
            linked.technology_code,
            parent.technology_code,
            MilestoneEvent.milestone_event_id,
            MilestoneEvent.milestone_type_code,
            MilestoneEvent.event_date,
            MilestoneEvent.event_year,
            MilestoneTechnology.relevance_score,
        )
        .join(
            MilestoneTechnology,
            MilestoneTechnology.milestone_event_id == MilestoneEvent.milestone_event_id,
        )
        .join(linked, linked.technology_node_id == MilestoneTechnology.technology_node_id)
        .outerjoin(parent, parent.technology_node_id == linked.parent_technology_node_id)
        .where(MilestoneEvent.verification_status_code == "verified")
    ).all()

    grouped: dict[str, dict[int, DatedEvent]] = defaultdict(dict)
    for code, parent_code, event_id, type_code, event_date, event_year, relevance in rows:
        target = code if code.count(".") == 1 else parent_code
        if target is None or target.count(".") != 1:
            continue
        occurred = event_date
        if occurred is None:
            if event_year is None:
                continue
            # 只知年份的按年中处理，与 import_release_milestones 的约定一致。
            occurred = date(int(event_year), 7, 1)
        # 同一事件可能链到多个 L3，按事件去重，一次突破不重复计数。
        grouped[target][event_id] = DatedEvent(
            event_id=event_id,
            event_type_code=type_code,
            occurred_on=occurred,
            relevance=float(relevance) / 100,
            source_quality=0.6,
        )
    return {code: list(events.values()) for code, events in grouped.items()}


def _l2_foresight(db: Session, run: DiscoveryRun) -> dict[str, ForesightResult]:
    """算出每个 L2 技术方向的成熟度轨迹与跨越时点，并给出全局名次。"""
    names = {
        code: name
        for code, name in db.execute(
            select(TechnologyNode.technology_code, TechnologyNode.technology_name).where(
                TechnologyNode.taxonomy_version_id == run.taxonomy_version_id,
                TechnologyNode.level_code == "L2",
            )
        )
    }
    results = [
        compute_foresight(
            technology_code=code,
            technology_name=names.get(code, code),
            events=events,
            as_of=run.target_date,
        )
        for code, events in sorted(l2_dated_events(db).items())
        if code in names
    ]
    return {item.technology_code: item for item in rank_foresight(results)}


def _l2_job_demand(db: Session, parse_run_id: int) -> dict[str, int]:
    """每个 L2 技术方向当前被多少份 JD 提及。

    与前瞻的「何时成熟」互补：这一项回答的是**市场现在有多热**，而不是何时会热。
    在时滞无法标定的情况下，现状比预测可靠得多。
    """
    node = aliased(TechnologyNode)
    parent = aliased(TechnologyNode)
    rows = db.execute(
        select(parent.technology_code, JobRequirement.job_posting_id)
        .join(node, node.technology_node_id == JobRequirement.technology_node_id)
        .join(parent, parent.technology_node_id == node.parent_technology_node_id)
        .join(
            TechnologyMatchAssessment,
            TechnologyMatchAssessment.job_requirement_id == JobRequirement.job_requirement_id,
        )
        .where(
            TechnologyMatchAssessment.job_parse_run_id == parse_run_id,
            TechnologyMatchAssessment.assessment_status_code == "accepted",
        )
        .distinct()
    ).all()
    counts: dict[str, set[int]] = defaultdict(set)
    for code, job_id in rows:
        if code and code.count(".") == 1:
            counts[code].add(job_id)
    return {code: len(jobs) for code, jobs in counts.items()}


def _classify_candidate(
    nearest: "_NearestRole", foresight_block: dict, maturity_stage: str
) -> str:
    """把候选归入四类之一，用**覆盖率与 Jaccard 两个轴**。

    单用非对称覆盖率不成立：它在所有岗位画像上取最大值，加画像只会让它升不会降。
    实测岗位画像从 448 涨到 676 之后，100 个候选的覆盖率全部到 1.0，四个分类塌成
    一个。候选只有 2–3 个技术、岗位画像有 4–8 个，库一密集就必然饱和。

    第二个轴解决的正是这件事。候选被完全包含时 Jaccard = |候选| / |岗位|，
    也就是候选占了这个岗位能力集的多大比例。于是两个轴各管一件事：

    - **覆盖率**：候选有没有既有岗位覆盖不了的能力。低 → 有新东西。
    - **Jaccard**：候选是不是这个岗位的**全部**，还是只占其中一小块。

    ROLE_SCOPE_JACCARD = 0.5 的含义是「候选至少要占到最近岗位能力集的一半」，
    这不是拟合出来的阈值而是一个可解释的口径：占不到一半说明候选只是那个岗位的
    一个片段，把它判成「就是那个岗位」是错的，它属于岗位能力的局部演化。
    """
    if nearest.coverage >= EXISTING_ROLE_COVERAGE:
        # 能力全被吸收，再看范围：占了大半才算同一岗位，否则只是它的一个片段。
        return "existing_role" if nearest.jaccard >= ROLE_SCOPE_JACCARD else "role_evolution"
    if nearest.coverage >= ROLE_EVOLUTION_COVERAGE:
        return "role_evolution"
    directions = foresight_block.get("directions") or []
    all_crossed = bool(directions) and all(item["crossed"] for item in directions)
    if all_crossed and maturity_stage != "potential":
        return "library_gap"
    return "potential_new_role"


def _nearest_role_card(db: Session, nearest: "_NearestRole") -> dict | None:
    """最邻近岗位的可读信息。

    此前机械卡里只有一个 `nearest_role_overlap` 数字，既没有岗位名也没有它的能力
    清单——前端无从展示「跟谁比」，LLM 写「与既有岗位的差异」时也没有可比的对象，
    结果只能去谈命名本身。
    """
    if nearest.role_id is None:
        return None
    role = db.get(JobRole, nearest.role_id)
    if role is None:
        return None
    return {
        "role_code": role.role_code,
        "role_name": role.canonical_name,
        "coverage": round(nearest.coverage, 3),
        "jaccard": round(nearest.jaccard, 3),
        "role_technology_count": nearest.role_technology_count,
        "shared_technology_count": nearest.shared_technology_count,
    }


def _candidate_foresight(
    technology_codes: tuple[str, ...],
    foresight: dict[str, ForesightResult],
    demand: dict[str, int],
    as_of: date,
    lag_prior: dict | None = None,
) -> dict:
    """把候选依托的各 L2 方向的前瞻判断汇成一个块。

    **主语是技术方向，不是岗位。** 候选依托多个方向，岗位真正出现还取决于这些方向
    是否被同一批雇主组合进同一个职位，那不在本模块的推断范围内。

    块里有三类时间信息，**可信度依次递减，前端必须分开呈现**：

    1. `foundation_from` / `foundation_to` / `foundation_ready_months`——技术地基
       成型区间。由真实里程碑日期算出的跨越时点取最早与最晚，零假设。
    2. `directions[].jd_demand` / `demand_rank`——各方向当前的招聘需求与名次。
       是对现状的观测，同样零假设。
    3. `reference_window`——**由外部先验推出的参考窗口，不是本系统的测量结果。**
       见 `TRANSMISSION_LAG_PRIOR_MONTHS` 的说明：时滞标定在自有数据上失败了，
       这个区间纯粹是「最后一个方向成熟的时点 + 先验时滞」，带
       `external_prior_not_measured` 标记下发，前端必须显著标注来源。
    """
    directions = sorted({code.rsplit(".", 1)[0] for code in technology_codes if "." in code})
    ranking = list(foresight)
    demand_order = sorted(demand, key=lambda code: -demand.get(code, 0))
    blocks = []
    for code in directions:
        result = foresight.get(code)
        if result is None:
            continue
        blocks.append({
            "technology_code": code,
            "technology_name": result.technology_name,
            "crossed": result.crossing_date is not None,
            "crossing_month": (
                result.crossing_date.strftime("%Y-%m") if result.crossing_date else None
            ),
            "peak_maturity": round(result.peak_maturity, 3),
            "milestone_count": result.event_count,
            "foresight_rank": ranking.index(code) + 1,
            "jd_demand": demand.get(code, 0),
            "demand_rank": demand_order.index(code) + 1 if code in demand else None,
            "demand_total_directions": len(demand_order),
            "statement": horizon_label(result, as_of),
        })

    crossed = [item for item in blocks if item["crossed"]]
    all_crossed = bool(blocks) and len(crossed) == len(blocks)
    months = sorted(item["crossing_month"] for item in crossed)
    latest_date = max(
        (foresight[item["technology_code"]].crossing_date for item in crossed),
        default=None,
    )
    ready_months = (
        round((as_of - latest_date).days / 30.44, 1) if all_crossed and latest_date else None
    )

    # 时滞先验按技术类型取，而不是一个拉平的区间。算法类的工程化节奏本就快于
    # 硬件类，用同一个区间套所有候选，等于把最快和最慢的技术当成一回事。
    # 分类型的区间由 estimate_transmission_lag 给出，候选卡里本来就在算，
    # 此前没被窗口用上——窗口用的是一个拍出来的 12–36 月。
    window = None
    typed = lag_prior if lag_prior and lag_prior.get("status") == "reference_prior" else None
    low, high = (
        (typed["low_months"], typed["high_months"]) if typed else TRANSMISSION_LAG_PRIOR_MONTHS
    )
    if all_crossed and latest_date is not None:
        window = {
            "from": _shift_month(latest_date, round(low)).strftime("%Y-%m"),
            "to": _shift_month(latest_date, round(high)).strftime("%Y-%m"),
            "prior_months": [low, high],
            "anchor_month": latest_date.strftime("%Y-%m"),
            "technology_classes": typed["technology_classes"] if typed else [],
            "coefficient": typed["coefficient"] if typed else None,
        }

    return {
        "schema_version": "candidate_foresight_v2",
        "threshold": JOBIFICATION_THRESHOLD,
        # θ 是设定值：曾尝试从横截面标定但失败（秩相关 −0.268、84.3% 取值重复）。
        # 排序对它稳健（θ 在 0.25–0.45 间扫动，相邻秩相关 0.857–0.958），
        # 但单个方向的跨越时点不稳（极差最大 30 个月），故只报名次与阶段。
        "threshold_origin": "configured_not_measured",
        # ① 技术地基成型区间：零假设，由真实跨越时点算出。
        "foundation_from": months[0] if months else None,
        "foundation_to": months[-1] if months else None,
        "foundation_complete": all_crossed,
        "foundation_ready_months": ready_months,
        # ③ 参考窗口：**外部先验**，不是测量结果。见 TRANSMISSION_LAG_PRIOR_MONTHS。
        "reference_window": window,
        "reference_window_origin": (
            "typed_external_prior_not_measured" if typed else "external_prior_not_measured"
        ),
        "reference_window_reason": (
            "区间 = 技术地基就位时点 + 该技术类型的传导时滞先验。"
            "**先验来自外部参考研究的分类型实测区间（算法类 10–15 月、系统集成类 "
            "12–18 月、硬件类 15–24 月，另乘类型修正系数），不是本系统的测量结果。**"
            "本项目 JD 侧的时间跨度仅约 10 周且为采集时间而非发布时间，"
            "无法测出 10–24 个月量级的时滞，因此该区间可用但无法在本系统内验证。"
        ),
        "directions": sorted(blocks, key=lambda item: item["foresight_rank"]),
        "crossed_direction_count": len(crossed),
        "best_foresight_rank": min((item["foresight_rank"] for item in blocks), default=None),
    }


def _shift_month(anchor: date, months: int) -> date:
    """按月推移，统一落在月中——只做月级推演，不伪造具体某一天。"""
    total = anchor.month - 1 + months
    return date(anchor.year + total // 12, total % 12 + 1, 15)


def _milestone_signals_by_node(
    db: Session, run: DiscoveryRun
) -> dict[int, list[MaturityEventSignal]]:
    """一次取回全部已核实里程碑，按**本次词表版本**的技术节点分组。

    里程碑的技术链接建立在导入当时的词表版本上，而推演跑在当前版本上。
    节点 id 逐版本独立，直接按 id 分组会让新版本的节点一个信号都取不到——
    成熟度因此恒为 0，`emerging` 档的成熟度条件永远不可能满足。
    技术编码跨版本稳定，故按编码把链接重映射到本次版本的节点上。
    """
    linked_node = aliased(TechnologyNode)
    rows = db.execute(
        select(
            linked_node.technology_code,
            MilestoneEvent.milestone_event_id,
            MilestoneEvent.milestone_type_code,
            MilestoneEvent.event_date,
            MilestoneEvent.event_year,
            MilestoneTechnology.relevance_score,
            func.avg(EvidenceSpan.source_reliability_score),
        )
        .join(
            MilestoneTechnology,
            MilestoneTechnology.milestone_event_id == MilestoneEvent.milestone_event_id,
        )
        .join(
            linked_node,
            linked_node.technology_node_id == MilestoneTechnology.technology_node_id,
        )
        .outerjoin(
            MilestoneEvidence,
            MilestoneEvidence.milestone_event_id == MilestoneEvent.milestone_event_id,
        )
        .outerjoin(
            EvidenceSpan, EvidenceSpan.evidence_span_id == MilestoneEvidence.evidence_span_id
        )
        .where(
            MilestoneEvent.verification_status_code == "verified",
            _within_target_date(run.target_date),
        )
        .group_by(
            linked_node.technology_code,
            MilestoneEvent.milestone_event_id,
            MilestoneEvent.milestone_type_code,
            MilestoneEvent.event_date,
            MilestoneEvent.event_year,
            MilestoneTechnology.relevance_score,
        )
    ).all()
    # 技术编码 → 本次词表版本的节点 id
    node_by_code = {
        code: node_id
        for code, node_id in db.execute(
            select(TechnologyNode.technology_code, TechnologyNode.technology_node_id).where(
                TechnologyNode.taxonomy_version_id == run.taxonomy_version_id
            )
        )
    }
    grouped: dict[int, list[MaturityEventSignal]] = defaultdict(list)
    for code, event_id, type_code, event_date, event_year, relevance, source_quality in rows:
        node_id = node_by_code.get(code)
        if node_id is None:
            # 该技术点在本版词表中已下线，其里程碑证据不再参与本次推演。
            continue
        grouped[node_id].append(
            MaturityEventSignal(
                event_id=event_id,
                event_type_code=type_code,
                age_years=_event_age_years(run.target_date, event_date, event_year),
                relevance=float(relevance) / 100,
                source_quality=float(source_quality or 60) / 100,
            )
        )
    return grouped


def _within_target_date(target_date: date):
    """event_date 可空、event_year 必填，只有年份的里程碑同样是有效证据。"""
    return or_(
        MilestoneEvent.event_date <= target_date,
        (MilestoneEvent.event_date.is_(None)) & (MilestoneEvent.event_year <= target_date.year),
    )


def _event_age_years(target_date: date, event_date: date | None, event_year: int) -> float:
    if event_date is not None:
        return max(0.0, (target_date - event_date).days / 365.25)
    # 只知道年份时按年中取值，避免把整年证据当成年初或年末。
    return max(0.0, target_date.year - event_year + 0.5)


def _inherited_signals(
    technology_id: int,
    by_node: dict[int, list[MaturityEventSignal]],
    ancestors: dict[int, tuple[int, ...]],
    decay: float,
) -> tuple[list[MaturityEventSignal], bool]:
    """自身证据优先；缺失的部分按祖先距离折减后补入。返回 (信号, 是否有直接证据)。"""
    signals: dict[int, MaturityEventSignal] = {
        signal.event_id: signal for signal in by_node.get(technology_id, [])
    }
    direct = bool(signals)
    for distance, ancestor_id in enumerate(ancestors.get(technology_id, ()), start=1):
        factor = decay**distance
        for signal in by_node.get(ancestor_id, []):
            # 复合主键要求每个里程碑在一个快照里只出现一次，就近继承的权重更高。
            if signal.event_id in signals:
                continue
            signals[signal.event_id] = MaturityEventSignal(
                event_id=signal.event_id,
                event_type_code=signal.event_type_code,
                age_years=signal.age_years,
                relevance=signal.relevance * factor,
                source_quality=signal.source_quality,
            )
    return list(signals.values()), direct


def _persist_maturity(
    db: Session,
    run: DiscoveryRun,
    selected_ids: list[int],
    parameters: dict,
    ancestors: dict[int, tuple[int, ...]],
) -> dict[int, float]:
    technology_ids = selected_ids or list(
        db.scalars(
            select(TechnologyNode.technology_node_id).where(
                TechnologyNode.taxonomy_version_id == run.taxonomy_version_id,
                TechnologyNode.governance_status_code == "active",
            )
        )
    )
    by_node = _milestone_signals_by_node(db, run)
    alpha = float(parameters.get("maturity_alpha", 0.17))
    decay = float(parameters.get("ancestor_inheritance_decay", 0.6))
    exploration_floor = float(parameters.get("exploration_floor", 0.15))
    result = {}
    for technology_id in technology_ids:
        signals, direct = _inherited_signals(technology_id, by_node, ancestors, decay)
        maturity = calculate_maturity(signals, alpha=alpha, exploration_floor=exploration_floor)
        if not signals:
            status = "missing_verified_milestone"
        elif direct:
            status = "verified"
        else:
            status = "inherited_from_ancestor"
        snapshot = TechnologyMaturitySnapshot(
            discovery_run_id=run.discovery_run_id,
            technology_node_id=technology_id,
            maturity_raw_score=Decimal(str(maturity.raw)),
            maturity_explore_score=Decimal(str(maturity.explore)),
            verified_event_count=len(signals),
            evidence_status_code=status,
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
    ancestors: dict[int, tuple[int, ...]],
    min_role_technology_count: int,
    excluded_role_ids: frozenset[int],
) -> IndustryTask:
    responsibility = _representative_responsibility(evidence.responsibilities)
    market = calculate_market_support(
        job_count=len(evidence.job_ids),
        organization_count=len(evidence.organization_ids),
        source_count=len(evidence.source_ids),
        observation_window_count=len(evidence.observation_windows),
        application_evidence_count=_application_evidence_count(db, run, technology_ids, ancestors),
    )
    coverage = _existing_role_coverage(
        db,
        technology_ids,
        run.target_date,
        min_role_technology_count=min_role_technology_count,
        excluded_role_ids=excluded_role_ids,
    )
    evidence_strength = min(1.0, 0.35 + 0.08 * len(evidence.evidence_job_ids))
    maturity_score = sum(maturity.get(item, 0) for item in technology_ids) / len(technology_ids)
    gap = calculate_task_gap(
        maturity=max(0.15, maturity_score),
        existing_role_coverage=coverage,
        evidence_strength=evidence_strength,
        organization_count=len(evidence.organization_ids),
        market_support=market,
    )
    text = (responsibility.normalized_task_text or "").strip() if responsibility else ""
    # 没有可用职责时用技术名兜底，而不是拼技术节点 ID（ID 对使用者没有意义）。
    fallback = (
        " / ".join(
            db.scalars(
                select(TechnologyNode.technology_name)
                .where(TechnologyNode.technology_node_id.in_(technology_ids))
                .order_by(TechnologyNode.technology_code)
            )
        )
        or "技术组合工程任务"
    )
    task = IndustryTask(
        discovery_run_id=run.discovery_run_id,
        task_code=f"task_{_stable_digest(technology_ids)[:20]}",
        task_name=text or fallback,
        normalized_task_text=text or fallback,
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
        evidence_status_code=(
            ("traceable" if evidence.evidence_job_ids else "missing_span")
            if text
            # 无可用 JD 职责，任务文本由技术名兜底，语义可靠度低。
            else "technology_fallback_text"
        ),
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
    ancestors: dict[int, tuple[int, ...]],
    foresight: dict[str, ForesightResult],
    technology_frequency: dict[int, int],
    job_demand: dict[str, int],
    candidate_key: str,
    min_role_technology_count: int,
    excluded_role_ids: frozenset[int],
    existing: EmergingRoleCandidate | None = None,
) -> bool:
    """写入或刷新候选，返回是否复用了既有候选。"""
    technologies = list(
        db.scalars(
            select(TechnologyNode)
            .where(TechnologyNode.technology_node_id.in_(technology_ids))
            .order_by(TechnologyNode.level_code.desc(), TechnologyNode.technology_code)
        )
    )
    names = [item.technology_name for item in technologies]
    proposed_name = _mechanical_name(names)
    application_count = _application_evidence_count(db, run, technology_ids, ancestors)
    raw_maturity = sum(maturity.get(item, 0) for item in technology_ids) / len(technology_ids)
    signals = CandidateSignals(
        publication_task_gap=float(task.task_gap_score),
        community_cohesion=_combination_cohesion(
            technology_ids, len(evidence.job_ids), technology_frequency
        ),
        market_support=float(task.market_support_score),
        technology_maturity=raw_maturity,
        temporal_growth_stability=min(1.0, len(evidence.observation_windows) / 3),
        evidence_completeness=_evidence_completeness(
            evidence=evidence,
            application_count=application_count,
            has_real_responsibility=task.evidence_status_code != "technology_fallback_text",
            milestone_backed=raw_maturity > 0,
        ),
        novelty=1 - float(task.existing_role_coverage_score),
        job_count=len(evidence.job_ids),
        organization_count=len(evidence.organization_ids),
        source_count=len(evidence.source_ids),
        observation_window_count=len(evidence.observation_windows),
        application_evidence_count=application_count,
    )
    scored = score_candidate(signals)
    nearest = _nearest_role(
        db,
        technology_ids,
        run.target_date,
        min_role_technology_count=min_role_technology_count,
        excluded_role_ids=excluded_role_ids,
    )
    nearest_role_id, overlap = nearest.role_id, nearest.coverage
    nearest_role_card = _nearest_role_card(db, nearest)
    lag_prior = estimate_transmission_lag(
        tuple(item.technology_code.split(".")[0] for item in technologies)
    )
    foresight_block = _candidate_foresight(
        tuple(item.technology_code for item in technologies),
        foresight,
        job_demand,
        run.target_date,
        lag_prior,
    )
    classification = _classify_candidate(nearest, foresight_block, scored.maturity_stage)
    mechanical = {
        "fact_schema_version": "mechanical_role_card_v2",
        "task_text": task.normalized_task_text,
        # jd_responsibility：来自真实 JD 职责；technology_fallback：无可用职责，
        # 由技术名拼接兜底，语义可靠度低，表达层应据此决定是否采用。
        "task_text_source": (
            "technology_fallback"
            if task.evidence_status_code == "technology_fallback_text"
            else "jd_responsibility"
        ),
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
        "nearest_role": nearest_role_card,
        # 先验估计，非本项目观测值：JD 侧尚无跨月真实采集，无法自行估计时滞。
        "expected_transmission_lag": lag_prior,
        "foresight": foresight_block,
        "evidence_ids": sorted(evidence.evidence_job_ids),
        "llm_boundary": "expression_only_no_fact_mutation",
    }
    if existing is not None:
        # 未决候选就地刷新：保留 candidate_code、表达层与审批任务，只更新机械事实。
        mechanical["first_seen_run_code"] = (existing.mechanical_card_json or {}).get(
            "first_seen_run_code"
        ) or run.run_code
        mechanical["last_seen_run_code"] = run.run_code
        existing.task_community_id = community.task_community_id
        existing.maturity_stage_code = scored.maturity_stage
        existing.candidate_score = Decimal(str(scored.score))
        existing.nearest_job_role_id = nearest_role_id
        existing.overlap_score = Decimal(str(overlap))
        existing.classification_code = classification
        existing.mechanical_card_json = mechanical
        existing.last_seen_discovery_run_id = run.discovery_run_id
        existing.risk_flags_json = list(scored.risk_flags)
        db.query(CandidateScoreComponent).filter(
            CandidateScoreComponent.emerging_role_candidate_id
            == existing.emerging_role_candidate_id
        ).delete(synchronize_session=False)
        db.query(CandidateTechnology).filter(
            CandidateTechnology.emerging_role_candidate_id == existing.emerging_role_candidate_id
        ).delete(synchronize_session=False)
        _persist_candidate_children(db, existing, scored, technology_ids, evidence)
        db.flush()
        return True

    mechanical["first_seen_run_code"] = run.run_code
    mechanical["last_seen_run_code"] = run.run_code
    candidate = EmergingRoleCandidate(
        discovery_run_id=run.discovery_run_id,
        task_community_id=community.task_community_id,
        candidate_code=f"candidate_{uuid4().hex[:20]}",
        candidate_key=candidate_key,
        proposed_name=proposed_name,
        normalized_name=_normalize_name(proposed_name),
        maturity_stage_code=scored.maturity_stage,
        workflow_status_code="pending",
        candidate_score=Decimal(str(scored.score)),
        support_job_count=len(evidence.job_ids),
        nearest_job_role_id=nearest_role_id,
        overlap_score=Decimal(str(overlap)),
        classification_code=classification,
        mechanical_card_json=mechanical,
        last_seen_discovery_run_id=run.discovery_run_id,
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
    _persist_candidate_children(db, candidate, scored, technology_ids, evidence)
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
    return False


def _persist_candidate_children(
    db: Session,
    candidate: EmergingRoleCandidate,
    scored,
    technology_ids: tuple[int, ...],
    evidence: _PairEvidence,
) -> None:
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
                membership_code="core",
            )
        )
    _persist_candidate_profile(db, candidate, technology_ids, evidence)


# 画像层要求技术在支撑 JD 中过半出现（见 _persist_candidate_profile 的阈值说明）。


def _persist_candidate_profile(
    db: Session,
    candidate: EmergingRoleCandidate,
    core_ids: tuple[int, ...],
    evidence: _PairEvidence,
) -> None:
    """在核心组合之外补一层「画像」：支撑 JD 中过半出现的技术。

    核心组合是挖掘出的频繁闭项集，只有 2–5 个技术——它足以定义候选的身份，
    但不足以生成一份可用的岗位描述。画像层把这批 JD 共有的其余能力补进来。

    **画像不参与候选身份、去重键与覆盖率测量**，那三者一律只看核心层，
    这样扩展画像不会改动 classification 阈值的既有标定。
    """
    support = len(evidence.job_ids)
    if not support:
        return
    # 取上取整而非下取整，并至少要求 2 份 JD：support=2 或 3 时 int(support*0.5) 等于 1，
    # 「过半」会退化成「任一支撑 JD 里出现过即可」，把噪声技术全拉进画像。
    threshold = max(2, -(-support // 2))
    core = set(core_ids)
    for technology_id, count in sorted(evidence.technology_counts.items()):
        if technology_id in core or count < threshold:
            continue
        db.add(
            CandidateTechnology(
                emerging_role_candidate_id=candidate.emerging_role_candidate_id,
                technology_node_id=technology_id,
                requirement_type_code="bonus",
                importance_score=Decimal(str(round(count / support, 4))),
                evidence_count=count,
                membership_code="profile",
            )
        )


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
        candidate_key=hashlib.sha256(f"name_inference|{query}".encode()).hexdigest()[:64],
        proposed_name=proposed_name,
        normalized_name=query,
        maturity_stage_code="confirmed" if role else "potential",
        workflow_status_code="merged" if role or historical_candidate else "pending",
        candidate_score=Decimal("100" if role else "40" if historical_candidate else "10"),
        nearest_job_role_id=role.job_role_id if role else None,
        overlap_score=Decimal("1" if role else "0"),
        classification_code=classification,
        last_seen_discovery_run_id=run.discovery_run_id,
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
    # **门禁按证据来源分支。**
    #
    # 这道门要挡的是「基础无法追溯的岗位被发布成正式定义」。原实现把「可追溯」
    # 写死成了 JD 派生的三件东西：任务社区、技术词、证据 JD 编号。前者与后者
    # 外部证据类**按定义就没有**——它们的立论恰恰是「JD 里从来没有过这个组合」，
    # 于是这两类候选在这道门下永远发布不了，报错还提示「缺少证据片段」，
    # 读起来像是数据没填好，实际是门禁问的问题不适用。
    #
    # 技术词是三类共同的硬要求，保留；可追溯性改为按来源各查各的证据。
    card = candidate.mechanical_card_json or {}
    if not technology_count:
        raise DiscoveryError("候选没有关联技术词，不能发布正式岗位")
    if candidate.classification_code in EXTERNAL_EVIDENCE_CLASSIFICATIONS:
        # 上游路径追溯到共现技术对，里程碑路径追溯到具体事件。
        if not (card.get("evidence_pairs") or card.get("milestones")):
            raise DiscoveryError(
                "外部证据类候选缺少上游共现对或里程碑事件，无法追溯来源，不能发布正式岗位"
            )
    elif not candidate.task_community_id or not card.get("evidence_ids"):
        raise DiscoveryError("候选缺少可追溯任务或证据 JD 片段，不能发布正式岗位")
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
                supporting_job_count=int(card.get("job_count", 0)),
                independent_organization_count=int(card.get("organization_count", 0)),
                independent_source_count=int(card.get("source_count", 0)),
                last_seen_at=None,
                confidence_score=candidate.candidate_score,
                is_human_edited=False,
            )
        )
    standard_content = {
        "title": candidate.proposed_name,
        "definition": version.one_line_definition,
        "responsibilities": expression.get("core_responsibilities") or [],
        # 外部证据类的卡里没有 technology_node_ids（它们的卡记的是技术编码），
        # 回落到候选—技术关联表，这对三条路径都成立且更准。
        "technology_node_ids": card.get("technology_node_ids")
        or [
            rel.technology_node_id
            for rel in db.scalars(
                select(CandidateTechnology).where(
                    CandidateTechnology.emerging_role_candidate_id
                    == candidate.emerging_role_candidate_id
                )
            )
        ],
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
                _within_target_date(target_date),
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
                TechnologyMatchAssessment.job_parse_run_id == clustering_run.job_parse_run_id,
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
        "job_parse_run_id": clustering_run.job_parse_run_id,
        "selected_technology_ids": selected_ids,
        "query_role_name": (query_role_name or "").strip() or None,
        "query_description": (query_description or "").strip() or None,
        "verified_milestone_ids": verified_ids,
        "verified_milestone_count": len(verified_ids),
        "approved_role_version_ids": approved_version_ids,
        "approved_role_count": len(approved_version_ids),
        "accepted_technology_assessment_ids": accepted_assessment_ids,
        "accepted_technology_assessment_count": len(accepted_assessment_ids),
        **_job_time_snapshot(db, cutoff),
        # 候选粒度由项集挖掘算法决定，换算法必然换候选，必须进输入快照。
        "itemset_algorithm_version": ITEMSET_ALGORITHM_VERSION,
        "parameters": parameters,
    }


def _job_time_snapshot(db: Session, cutoff: datetime) -> dict:
    """JD 采集时间决定观测窗，必须进输入快照。

    只记评估 ID 无法察觉时间戳变化：改采集时间不会改变"哪些评估通过 cutoff"，
    于是两个截然不同的数据状态会算出同一个哈希，重放检查直接返回上一次的结果。
    """
    rows = db.execute(
        select(JobPosting.job_posting_id, JobPosting.source_collected_at)
        .where(
            or_(
                JobPosting.source_collected_at <= cutoff,
                (JobPosting.source_collected_at.is_(None)) & (JobPosting.published_at <= cutoff),
            )
        )
        .order_by(JobPosting.job_posting_id)
    ).all()
    digest = hashlib.sha256()
    windows: set[str] = set()
    for job_posting_id, collected_at in rows:
        stamp = collected_at.isoformat() if collected_at else ""
        digest.update(f"{job_posting_id}:{stamp}\0".encode())
        if collected_at:
            windows.add(collected_at.strftime("%Y-%m"))
    return {
        "job_collection_time_hash": digest.hexdigest(),
        "job_collection_count": len(rows),
        "job_observation_windows": sorted(windows),
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


def _application_evidence_count(
    db: Session,
    run: DiscoveryRun,
    ids: tuple[int, ...],
    ancestors: dict[int, tuple[int, ...]] | None = None,
) -> int:
    # 与成熟度一致地上溯：应用类证据同样挂在 L1/L2，不展开则该门槛恒为 0。
    lookup = set(ids)
    for technology_id in ids:
        lookup.update((ancestors or {}).get(technology_id, ()))
    return int(
        db.scalar(
            select(func.count(func.distinct(MilestoneEvent.milestone_event_id)))
            .join(MilestoneTechnology)
            .where(
                MilestoneTechnology.technology_node_id.in_(sorted(lookup)),
                MilestoneEvent.verification_status_code == "verified",
                _within_target_date(run.target_date),
                MilestoneEvent.milestone_type_code.in_(
                    ["enterprise_application", "scaled_deployment", "product_release"]
                ),
            )
        )
        or 0
    )


def _role_capability_profiles(
    db: Session,
    target_date: date,
    *,
    min_technology_count: int,
    excluded_role_ids: frozenset[int] = frozenset(),
) -> list[tuple[int, set[int]]]:
    """取生效岗位版本的技术画像。

    技术词过少的版本不足以构成可比的岗位定义：当前 118 个岗位里有 32 个只有 1 个
    技术词（上游抽取稀疏所致），任何包含该词的技术组合与其重合度都会虚高，
    据此判定"已被既有岗位覆盖"是错误的。这类版本不参与最近岗位比较。

    excluded_role_ids 用于反事实分析（如留出重发现实验）：把指定岗位当作不存在。

    **按技术编码而非节点 id 比较。** 节点 id 是逐词表版本独立的，既有岗位版本的
    技术要求可能产自旧词表，而本次推演的候选来自新词表；按 id 比较会得到恒为空的
    交集，于是每个候选都被判成"全新岗位"。技术编码（T1.03.02 这类）跨版本稳定，
    是唯一可比的口径。
    """
    versions = list(
        db.scalars(
            select(JobRoleVersion).where(
                JobRoleVersion.approval_status_code == "approved",
                JobRoleVersion.valid_from <= target_date,
                or_(JobRoleVersion.valid_to.is_(None), JobRoleVersion.valid_to >= target_date),
            )
        )
    )
    profiles = []
    for version in versions:
        if version.job_role_id in excluded_role_ids:
            continue
        role_tech = set(
            db.scalars(
                select(TechnologyNode.technology_code)
                .join(
                    JobRoleVersionRequirement,
                    JobRoleVersionRequirement.technology_node_id
                    == TechnologyNode.technology_node_id,
                )
                .where(
                    JobRoleVersionRequirement.job_role_version_id == version.job_role_version_id
                )
            )
        )
        if len(role_tech) < min_technology_count:
            continue
        profiles.append((version.job_role_id, role_tech))
    return profiles


@dataclass(frozen=True)
class _NearestRole:
    """候选与最邻近既有岗位的比对结果。"""

    role_id: int | None
    coverage: float
    """非对称覆盖率 |候选∩岗位| / |候选|：候选的能力有多少已被该岗位吸收。"""
    jaccard: float
    """对称 Jaccard |候选∩岗位| / |候选∪岗位|：两者的范围有多接近。"""
    role_technology_count: int
    shared_technology_count: int


def _nearest_role(
    db: Session,
    technology_ids: tuple[int, ...],
    target_date: date,
    *,
    min_role_technology_count: int = 2,
    excluded_role_ids: frozenset[int] = frozenset(),
) -> _NearestRole:
    """找出与候选最接近的既有岗位，并同时给出两种度量。

    **为什么两个都要。** 非对称覆盖率回答「候选的能力有没有新东西」，Jaccard 回答
    「两者是不是同一个范围的岗位」，缺一不可：

    - 覆盖率单独用会随岗位库增长而饱和。它在所有画像上取最大值，加画像只会让它升、
      不会降——这是单调的。实测岗位画像从 448 涨到 676 之后，100 个候选里 100 个
      覆盖率都到了 1.0，分类彻底失去区分度。
    - 候选被完全包含时，Jaccard 恰好等于 |候选| / |岗位|，也就是**候选占了这个
      岗位能力集的多大比例**。两个技术的候选落在七个技术的岗位里，覆盖率满分，
      但 Jaccard 只有 0.29——它是那个岗位的一个片段，不是那个岗位。

    分档因此改为二维（见 `_classify_candidate`）：覆盖率决定「有没有新能力」，
    Jaccard 决定「是整个岗位还是岗位的一部分」。
    """
    target = set(
        db.scalars(
            select(TechnologyNode.technology_code).where(
                TechnologyNode.technology_node_id.in_(technology_ids or [-1])
            )
        )
    )
    if not target:
        return _NearestRole(None, 0.0, 0.0, 0, 0)
    best = _NearestRole(None, 0.0, 0.0, 0, 0)
    for role_id, role_tech in _role_capability_profiles(
        db,
        target_date,
        min_technology_count=min_role_technology_count,
        excluded_role_ids=excluded_role_ids,
    ):
        shared = len(target & role_tech)
        coverage = shared / len(target)
        union = len(target | role_tech)
        jaccard = shared / union if union else 0.0
        # 先比覆盖率，覆盖率相同时取范围更贴近的那个岗位——否则同为「完全包含」的
        # 候选会随机匹配到一个巨大的岗位上，差异说明也就无从谈起。
        if (coverage, jaccard) > (best.coverage, best.jaccard):
            best = _NearestRole(role_id, coverage, jaccard, len(role_tech), shared)
    return best


def _existing_role_coverage(
    db: Session,
    ids: tuple[int, ...],
    target_date: date,
    *,
    min_role_technology_count: int = 2,
    excluded_role_ids: frozenset[int] = frozenset(),
) -> float:
    return _nearest_role(
        db,
        ids,
        target_date,
        min_role_technology_count=min_role_technology_count,
        excluded_role_ids=excluded_role_ids,
    ).coverage


# 招聘平台注入到 JD 正文里的导航与自荐语，不是岗位职责。
RESPONSIBILITY_BOILERPLATE = (
    "猎聘",
    "我是猎头",
    "我是招聘方",
    "boss直聘",
    "智联招聘",
    "前程无忧",
    "扫码",
    "关注公众号",
    "投递简历",
    "简历发送",
)
MIN_RESPONSIBILITY_LENGTH = 8


def _is_usable_responsibility(item: JobResponsibility) -> bool:
    """结构完整、长度合理且不含招聘平台样板文字的职责才可作为代表。"""
    text = (item.normalized_task_text or item.raw_text or "").strip()
    if len(text) < MIN_RESPONSIBILITY_LENGTH:
        return False
    lowered = text.casefold()
    if any(mark in lowered for mark in RESPONSIBILITY_BOILERPLATE):
        return False
    return bool((item.action_verb or "").strip()) and bool((item.task_object or "").strip())


def _representative_responsibility(rows: list[JobResponsibility]) -> JobResponsibility | None:
    """选一条能代表该技术组合的职责。

    真实职责在各份 JD 中措辞互不相同、几乎都只出现一次，而招聘平台样板文字会
    跨 JD 重复出现。纯按出现频次排序会系统性地选中样板文字（实测某候选的定义
    被写成"负责猎聘APP 我是猎头 我是招聘方…"），因此先过滤不可用条目，
    再在可用条目内按频次、信息量和置信度排序。
    """
    usable = [item for item in rows if _is_usable_responsibility(item)]
    if not usable:
        return None
    counts = Counter((item.normalized_task_text or item.raw_text).strip() for item in usable)

    def rank(item: JobResponsibility) -> tuple:
        text = (item.normalized_task_text or item.raw_text).strip()
        return (-counts[text], -float(item.confidence_score or 0), -len(text), text)

    return sorted(usable, key=rank)[0]


def _candidate_key(mode_code: str, technology_codes: tuple[str, ...]) -> str:
    """候选身份 = 推演模式 + 技术组合，与运行、与词表版本都无关。

    **必须用技术编码而非节点 id。** 节点 id 是逐词表版本独立的：同一个技术组合
    在 v1.1 与 v1.2 下拿到不同的 id，算出的键因此不同，去重失效——同一组技术会
    被当成两个候选反复提出。实测在 227 个候选里造成 43 组、共 105 个重复条目，
    而且重复条目之间的分类还会互相矛盾（同名候选一个判 existing_role、
    一个判 role_evolution），因为它们各自在不同版本的词表下算过覆盖率。

    技术编码（T1.03.02 这类）跨版本稳定，是唯一能充当候选身份的口径。
    这是节点 id 被当作跨版本标识符使用的第五处，其余四处见
    `_nearest_role`、`_milestone_signals_by_node` 与两个实验脚本的历史修复。
    """
    payload = f"{mode_code}|" + "-".join(sorted(technology_codes))
    return hashlib.sha256(payload.encode()).hexdigest()[:64]


def _stable_digest(values: tuple[int, ...]) -> str:
    return hashlib.sha256("|".join(map(str, values)).encode()).hexdigest()


def _normalize_name(value: str) -> str:
    return re.sub(r"[\s\-_—/（）()]+", "", value.strip().lower())
