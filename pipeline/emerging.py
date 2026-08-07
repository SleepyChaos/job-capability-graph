"""技术演化驱动的新兴岗位发现引擎（阶段三，移植自 embodied-job-evolution-lab）。

路线：技术实体链接 → 里程碑成熟度 → 能力/任务构建 → 现有岗位覆盖度与任务缺口
     → 任务社区聚类 → 候选岗位七维评分（含证据链）。

改造点（相对 lab 原实现）：
1. DataRepository → UnifiedRepository：数据源从 lab 私有库切换为统一库 unified.db
   （technologies/milestones/capabilities/tasks/role_titles 由 import_emerging_data.py 导入；
   related_jobs 基于统一库 6,793 条具身 JD 的 jd_text 别名召回）
2. LLM provider 的 llm 模式改用 pipeline/llm.py（统一 OPENAI_API_KEY），
   保留"任务必须携带证据关键词否则过滤"的防幻觉约束
3. 运行记录落 emerging_runs 表（替代 lab 的 JSON 文件持久化）
4. 候选岗位可提交 job_definitions（review_status=pending）对接审核闭环
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import uuid
from collections import defaultdict
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Any

from . import llm

# 事件类型 → 成熟度权重（移植自 lab algorithm.EVENT_WEIGHTS）
EVENT_WEIGHTS = {
    "技术演示": 0.45,
    "论文发表": 0.55,
    "技术突破": 0.68,
    "开源发布": 0.76,
    "产品发布": 0.84,
    "平台/工具发布": 0.88,
    "企业事件": 0.92,
    "标准/政策": 0.72,
    "其他": 0.35,
}

# 任务分组需与知识层 role_titles/tasks 对齐
VALID_TASK_GROUPS = ("data", "model", "evaluation", "deployment", "planning")
DEFAULT_TASK_GROUP = "model"


def _normalize(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", value or "").lower()


def _root_code(technology: dict[str, Any]) -> str:
    return technology.get("parent_id") or technology["technology_id"]


def _event_date(value: str) -> date | None:
    try:
        return datetime.fromisoformat(value[:10]).date()
    except (TypeError, ValueError):
        return None


def maturity_score(milestones: list[dict[str, Any]], target_date: date) -> tuple[float, list[dict[str, Any]]]:
    """技术成熟度：事件类型权重 × 相关度 × 时间衰减 exp(-0.11·年)，饱和映射 1-exp(-0.12·Σ)。"""
    contributions = []
    total = 0.0
    for event in milestones:
        event_date = _event_date(event["event_date"] or "")
        if not event_date or event_date > target_date:
            continue
        years = max(0.0, (target_date - event_date).days / 365.25)
        recency = math.exp(-0.11 * years)
        type_weight = EVENT_WEIGHTS.get(event.get("event_type") or "其他", 0.4)
        contribution = type_weight * event["relevance"] * recency
        total += contribution
        contributions.append(event | {"maturity_contribution": round(contribution, 4)})
    score = 1 - math.exp(-0.12 * total)
    contributions.sort(key=lambda item: item["maturity_contribution"], reverse=True)
    return round(min(0.98, score), 4), contributions[:12]


def _snippet(text: str, keywords: list[str], max_len: int = 170) -> str:
    compact = re.sub(r"\s+", " ", text)
    lower = compact.lower()
    positions = [lower.find(k.lower()) for k in keywords if k and lower.find(k.lower()) >= 0]
    start = max(0, (min(positions) if positions else 0) - 40)
    return compact[start:start + max_len] + ("…" if len(compact) > start + max_len else "")


# ---------------------------------------------------------------------------
# 统一库数据仓库（替代 lab DataRepository）
# ---------------------------------------------------------------------------

class UnifiedRepository:
    """从 unified.db 读取技术演化域数据与岗位语料；接口与 lab DataRepository 对齐。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # ---- 技术实体 ----

    def _tech_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "technology_id": row["technology_id"],
            "standard_name": row["standard_name"],
            "level": row["level"],
            "domain": row["domain"],
            "definition": row["definition"],
            "parent_id": row["parent_id"],
            "aliases": json.loads(row["aliases_json"] or "[]"),
        }

    def get_technology(self, technology_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM technologies WHERE technology_id = ?", (technology_id,)
        ).fetchone()
        return self._tech_row(row) if row else None

    def search_technologies(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        query_norm = _normalize(query)
        if not query_norm:
            return []
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in self.conn.execute(
            "SELECT * FROM technologies WHERE level IN ('L2','L3') ORDER BY level, technology_id"
        ).fetchall():
            tech = self._tech_row(row)
            name_norm = _normalize(tech["standard_name"])
            text_norm = " ".join([name_norm, _normalize(tech["definition"] or ""),
                                  *[_normalize(a) for a in tech["aliases"][:24]]])
            if query_norm == name_norm:
                score = 1.0
            elif query_norm in name_norm or name_norm in query_norm:
                score = 0.94
            elif query_norm in text_norm:
                score = 0.86
            else:
                score = SequenceMatcher(None, query_norm, name_norm).ratio() * 0.72
            if score >= 0.34:
                scored.append((score, tech))
        scored.sort(key=lambda item: (-item[0], item[1]["level"], item[1]["technology_id"]))
        return [tech | {"link_confidence": round(score, 3)} for score, tech in scored[:limit]]

    # ---- 里程碑 ----

    def milestones_for(self, technology: dict[str, Any]) -> list[dict[str, Any]]:
        code = technology["technology_id"]
        root_code = code.rsplit(".", 1)[0] if technology.get("level") == "L3" else code
        terms = [_normalize(technology["standard_name"]),
                 *[_normalize(a) for a in technology.get("aliases", [])[:12]]]
        matched = []
        for row in self.conn.execute("SELECT * FROM milestones").fetchall():
            links = json.loads(row["technology_links"] or "[]")
            bridge_score = max(
                (weight for linked_code, weight in links
                 if root_code.startswith(linked_code) or linked_code.startswith(root_code)),
                default=0.0,
            )
            event_text = _normalize((row["name"] or "") + (row["description"] or "")
                                    + (row["technology_category"] or ""))
            lexical_score = 0.72 if any(t and t in event_text for t in terms) else 0.0
            score = max(bridge_score, lexical_score)
            if score:
                matched.append(dict(row) | {"relevance": round(score, 3)})
        matched.sort(key=lambda item: (item["event_date"] or "", item["relevance"]), reverse=True)
        return matched

    # ---- 岗位召回（统一库 jobs，别名证据匹配）----

    def related_jobs(self, technology: dict[str, Any], max_rows: int = 600) -> list[dict[str, Any]]:
        standard_name = technology["standard_name"]
        root_terms = [standard_name, *technology.get("aliases", [])[:20]]
        root_terms.extend(re.split(r"与|及|和|、|/", standard_name))
        normalized_terms = {_normalize(t) for t in root_terms if len(_normalize(t)) >= 2}
        candidates = []
        for job in self.conn.execute(
            "SELECT job_id, title, company, city, salary_text, jd_text, link FROM jobs"
        ).fetchall():
            jd_text = job["jd_text"] or ""
            text_norm = _normalize(jd_text)
            evidence_terms = [t for t in normalized_terms if t in text_norm]
            if not evidence_terms:
                continue
            evidence_score = min(1.0, 0.5 + 0.12 * len(evidence_terms))
            candidates.append(dict(job) | {
                "technology_evidence_score": round(evidence_score, 3),
                "matched_terms": evidence_terms[:5],
            })
        candidates.sort(key=lambda item: item["technology_evidence_score"], reverse=True)
        return candidates[:max_rows]

    # ---- 算法知识层 ----

    def capabilities_for(self, root_code: str) -> list[dict[str, str]]:
        rows = self.conn.execute(
            "SELECT name, object, scenario FROM capabilities WHERE technology_code = ?", (root_code,)
        ).fetchall()
        return [dict(r) for r in rows]

    def fallback_capabilities(self) -> list[dict[str, str]]:
        return self.capabilities_for("fallback")

    def tasks_for(self, root_code: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT name, task_group, keywords_json, relevance FROM tasks WHERE technology_code = ?",
            (root_code,),
        ).fetchall()
        return [{"name": r["name"], "group": r["task_group"],
                 "keywords": json.loads(r["keywords_json"] or "[]"),
                 "relevance": float(r["relevance"])} for r in rows]

    def fallback_tasks(self) -> list[dict[str, Any]]:
        return self.tasks_for("fallback")

    def titles_for(self, root_code: str) -> dict[str, str]:
        rows = self.conn.execute(
            "SELECT task_group, title FROM role_titles WHERE technology_code = ?", (root_code,)
        ).fetchall()
        return {r["task_group"]: r["title"] for r in rows}


# ---------------------------------------------------------------------------
# LLM Provider 三模式（rule / mock / llm），llm 模式走 pipeline/llm.py
# ---------------------------------------------------------------------------

TASK_SYSTEM_PROMPT = (
    "你是具身智能产业岗位分析专家。根据给定技术实体与真实招聘 JD 证据，"
    "提炼该技术方向上正在出现的新兴产业任务。只输出 JSON 数组，不要任何解释。"
)


class RuleProvider:
    """规则模式：任务完全来自知识层数据库，不生成新任务。"""

    origin = "library"

    def extract_tasks(self, technology, evidence_jobs) -> list[dict[str, Any]]:
        return []

    def generate_definition(self, candidate: dict[str, Any]) -> str:
        tech = candidate.get("technology_name", "该技术")
        duties = candidate.get("responsibilities", [])
        duty_text = "、".join(duties[:3]) if duties else "相关技术研发"
        return (f"围绕{tech}方向，负责{duty_text}等工作，"
                f"面向{candidate.get('time_horizon', '1-3年')}内产业需求的新兴技术岗位。")


class MockProvider:
    """Mock 模式：确定性桩数据，验证动态生成链路。"""

    origin = "mock"

    def extract_tasks(self, technology, evidence_jobs) -> list[dict[str, Any]]:
        name = technology.get("standard_name", "该技术")
        return [
            {"name": f"[Mock]构建{name}产业应用验证流水线", "group": "deployment",
             "keywords": ["部署", "验证", "流水线", "应用"], "relevance": 0.88},
            {"name": f"[Mock]设计{name}跨场景泛化评测方案", "group": "evaluation",
             "keywords": ["评测", "泛化", "场景", "测试"], "relevance": 0.90},
        ]

    def generate_definition(self, candidate: dict[str, Any]) -> str:
        tech = candidate.get("technology_name", "该技术")
        return (f"[Mock生成] {tech}方向候选岗位：承担"
                f"{'、'.join(candidate.get('responsibilities', [])[:2]) or '相关研发'}职责。")


class LLMProvider:
    """真实大模型模式：证据约束 prompt（任务关键词必须来自传入 JD 证据），失败降级。"""

    origin = "llm"

    def extract_tasks(self, technology, evidence_jobs) -> list[dict[str, Any]]:
        job_lines = "\n".join(
            f"- 《{job.get('title', '未知岗位')}》：{str(job.get('jd_text', ''))[:300]}"
            for job in evidence_jobs[:8]
        ) or "（无直接证据岗位，请严格基于技术定义输出并降低 relevance）"
        user = (
            f"技术：{technology.get('standard_name', '')}（{technology.get('technology_id', '')}）\n"
            f"技术定义：{str(technology.get('definition', ''))[:200]}\n"
            f"相关岗位 JD 证据：\n{job_lines}\n\n"
            "要求：生成 3-5 条任务，每条包含字段 name（任务名称，15 字以内）、"
            f"group（必须为 {'/'.join(VALID_TASK_GROUPS)} 之一）、"
            "keywords（2-5 个关键词，**必须直接来自上述 JD 证据文本**，用于后续证据召回）、"
            "relevance（0.7-0.95 之间的小数）。仅输出 JSON 数组。"
        )
        parsed = llm.chat_json(TASK_SYSTEM_PROMPT, user)
        items = parsed if isinstance(parsed, list) else []
        tasks: list[dict[str, Any]] = []
        for item in items[:5]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            group = str(item.get("group", "")).strip().lower()
            keywords = [str(k).strip() for k in item.get("keywords", []) if str(k).strip()]
            if not name or not keywords:
                continue  # 防幻觉：无证据关键词的任务一律过滤
            if group not in VALID_TASK_GROUPS:
                group = DEFAULT_TASK_GROUP
            try:
                relevance = min(0.95, max(0.7, float(item.get("relevance", 0.85))))
            except (TypeError, ValueError):
                relevance = 0.85
            tasks.append({"name": name, "group": group, "keywords": keywords, "relevance": relevance})
        return tasks

    def generate_definition(self, candidate: dict[str, Any]) -> str:
        system = "你是人力资源专家，为新兴技术岗位撰写简明的岗位定义。只输出定义文本本身，不超过 80 字。"
        user = (
            f"技术方向：{candidate.get('technology_name', '')}\n"
            f"岗位名称：{candidate.get('job_title', '')}\n"
            f"核心职责：{'、'.join(candidate.get('responsibilities', [])[:3])}\n"
            f"必备技能：{'、'.join(candidate.get('required_skills', [])[:3])}\n"
            "请用 1-2 句话概括该岗位的定位与价值。"
        )
        text = llm.chat([{"role": "system", "content": system},
                         {"role": "user", "content": user}], temperature=0.4)
        if text and text.strip():
            return text.strip()
        return RuleProvider().generate_definition(candidate)


_PROVIDERS: dict[str, type] = {"rule": RuleProvider, "mock": MockProvider, "llm": LLMProvider}


def get_provider(mode: str | None):
    """按模式获取 provider；llm 模式未配置 Key 时自动降级为规则模式。"""
    if mode == "llm" and not llm.is_available():
        mode = "rule"
    return _PROVIDERS.get(mode or "rule", RuleProvider)()


# ---------------------------------------------------------------------------
# 核心算法（移植自 lab EmergingJobAlgorithm）
# ---------------------------------------------------------------------------

class EmergingJobAlgorithm:
    def __init__(self, repository: UnifiedRepository) -> None:
        self.repository = repository

    def run(
        self,
        technology_id: str,
        target_date: date,
        top_k: int = 5,
        config_id: str = "full",
        provider=None,
    ) -> dict[str, Any]:
        active_provider = provider or RuleProvider()
        technology = self.repository.get_technology(technology_id)
        if technology is None:
            raise ValueError(f"未找到技术实体：{technology_id}")

        milestones = self.repository.milestones_for(technology)
        maturity, maturity_evidence = maturity_score(milestones, target_date)
        maturity_factor = 1.0 if config_id == "no_maturity" else max(0.35, maturity)

        root = _root_code(technology)
        standard_name = technology["standard_name"]
        related_jobs = self.repository.related_jobs(technology)
        capabilities = [
            {**item,
             "name": item["name"].replace("{技术}", standard_name),
             "object": (item.get("object") or "").replace("{技术}", standard_name)}
            for item in (self.repository.capabilities_for(root) or self.repository.fallback_capabilities())
        ]
        library_tasks = self.repository.tasks_for(root)
        if library_tasks:
            task_specs = [{**t, "name": t["name"].replace("{技术}", standard_name), "origin": "library"}
                          for t in library_tasks]
        else:
            task_specs = []
            if active_provider.origin != "library":
                generated = active_provider.extract_tasks(technology, related_jobs)
                task_specs = [{**t, "origin": active_provider.origin} for t in generated
                              if t.get("name") and t.get("group") and t.get("keywords")]
            if not task_specs:
                task_specs = [{**t, "name": t["name"].replace("{技术}", standard_name), "origin": "library"}
                              for t in self.repository.fallback_tasks()]

        # 任务覆盖度与缺口评分
        task_results = []
        for index, task in enumerate(task_specs, start=1):
            evidence_jobs = []
            companies: set[str] = set()
            for job in related_jobs:
                jd_lower = (job["jd_text"] or "").lower()
                matches = [k for k in task["keywords"] if k.lower() in jd_lower]
                if matches and job["technology_evidence_score"] >= 0.45:
                    companies.add(job["company"] or "")
                    evidence_jobs.append({
                        "job_id": job["job_id"],
                        "title": job["title"],
                        "company": job["company"],
                        "snippet": _snippet(job["jd_text"], matches),
                        "source_url": job.get("link") or "",
                        "confidence": round(min(0.98, 0.55 + 0.08 * len(matches)
                                                + 0.2 * job["technology_evidence_score"]), 3),
                    })
            mentions = len(evidence_jobs)
            coverage = min(0.88, (1 - math.exp(-mentions / 8.0)) * 0.86)
            cross_company = min(1.0, len(companies) / 7.0)
            evidence_strength = min(1.0, 0.52 + min(0.24, len(milestones) / 120) + min(0.20, mentions / 35))
            gap = task["relevance"] * maturity_factor * (1 - coverage) * evidence_strength * (0.58 + 0.42 * cross_company)
            task_results.append(task | {
                "task_id": f"TASK-{root.replace('.', '')}-{index:02d}",
                "coverage": round(coverage, 4),
                "gap_score": round(gap, 4),
                "cross_company": round(cross_company, 4),
                "evidence_strength": round(evidence_strength, 4),
                "job_mentions": mentions,
                "company_count": len(companies),
                "job_evidence": evidence_jobs[:4],
            })

        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for task in task_results:
            groups[task["group"]].append(task)

        title_map = self.repository.titles_for(root)
        candidates = []
        existing_titles = [job["title"] for job in related_jobs[:300]]
        for order, (group, tasks) in enumerate(groups.items(), start=1):
            title = title_map.get(group) or f"{standard_name}{group.title()}工程师"
            max_overlap = max(
                (SequenceMatcher(None, title, existing).ratio() for existing in existing_titles if existing),
                default=0.0,
            )
            avg_gap = sum(t["gap_score"] for t in tasks) / len(tasks)
            avg_cross = sum(t["cross_company"] for t in tasks) / len(tasks)
            avg_evidence = sum(t["evidence_strength"] for t in tasks) / len(tasks)
            cohesion = min(0.96, 0.70 + 0.08 * len(tasks))
            technology_relevance = sum(t["relevance"] for t in tasks) / len(tasks)
            score = 100 * (
                0.20 * technology_relevance + 0.25 * avg_gap + 0.15 * cohesion
                + 0.10 * avg_cross + 0.10 * maturity_factor + 0.10 * avg_evidence
                + 0.10 * (1 - max_overlap)
            )
            if max_overlap >= 0.76:
                job_type = "已有岗位"
            elif max_overlap >= 0.56:
                job_type = "岗位演化"
            else:
                job_type = "新兴岗位"
            milestone_evidence = [{
                "event_id": item["event_id"], "name": item["name"],
                "event_date": item["event_date"], "source": item["source"],
                "snippet": (item["description"] or "")[:180], "confidence": item["relevance"],
            } for item in maturity_evidence[:3]]
            job_evidence = [ev for t in tasks for ev in t["job_evidence"][:2]][:4]
            candidates.append({
                "candidate_id": f"CAND-{technology_id.replace('.', '')}-{order:02d}",
                "job_title": title,
                "job_type": job_type,
                "score": round(score, 1),
                "time_horizon": "1-3年" if maturity >= 0.55 else "3-5年",
                "formation_reason": f"{standard_name}正在形成{group}类独立任务集合，现有岗位覆盖度不足。",
                "responsibilities": [t["name"] for t in tasks],
                "required_skills": self._skills(root, group),
                "bonus_skills": [],
                "application_scenarios": sorted({c["scenario"] for c in capabilities if c.get("scenario")})[:4],
                "job_definition": active_provider.generate_definition(
                    {"technology_name": standard_name, "job_title": title,
                     "responsibilities": [t["name"] for t in tasks],
                     "required_skills": self._skills(root, group),
                     "time_horizon": "1-3年" if maturity >= 0.55 else "3-5年"}
                ),
                "tasks": tasks,
                "scores": {
                    "technology_relevance": round(technology_relevance, 4),
                    "task_gap": round(avg_gap, 4),
                    "cohesion": round(cohesion, 4),
                    "cross_company": round(avg_cross, 4),
                    "maturity": round(maturity_factor, 4),
                    "evidence": round(avg_evidence, 4),
                    "existing_overlap": round(max_overlap, 4),
                },
                "evidence": {"milestones": milestone_evidence, "jobs": job_evidence},
                "evidence_path": [
                    {"type": "technology", "label": standard_name},
                    {"type": "capability", "label": capabilities[(order - 1) % len(capabilities)]["name"]},
                    {"type": "task", "label": tasks[0]["name"]},
                    {"type": "candidate", "label": title},
                ],
            })

        candidates.sort(key=lambda item: item["score"], reverse=True)
        candidates = candidates[:top_k]
        for rank, candidate in enumerate(candidates, start=1):
            candidate["rank"] = rank

        return {
            "technology": technology | {"maturity_score": maturity, "target_date": target_date.isoformat()},
            "capabilities": capabilities,
            "tasks": sorted(task_results, key=lambda item: item["gap_score"], reverse=True),
            "candidate_jobs": candidates,
            "metrics": {
                "evidence_completeness": round(sum(c["scores"]["evidence"] for c in candidates) / max(len(candidates), 1), 4),
                "task_cohesion": round(sum(c["scores"]["cohesion"] for c in candidates) / max(len(candidates), 1), 4),
                "existing_overlap": round(sum(c["scores"]["existing_overlap"] for c in candidates) / max(len(candidates), 1), 4),
                "related_job_count": len(related_jobs),
                "milestone_count": len(milestones),
            },
            "config_id": config_id,
            "generation_mode": active_provider.origin,
        }

    @staticmethod
    def _skills(root: str, group: str) -> list[str]:
        common = {
            "T1.02": ["世界模型", "多模态学习", "环境动力学", "机器人规划"],
            "T1.01": ["VLA", "多模态学习", "模仿学习", "机器人控制"],
            "T4.04": ["Sim-to-Real", "域随机化", "机器人仿真", "策略迁移"],
        }.get(root, ["具身智能", "数据分析", "系统工程"])
        group_skill = {
            "data": "数据工程", "model": "模型训练", "evaluation": "评测体系设计",
            "planning": "运动规划", "deployment": "推理部署",
        }.get(group, "技术研发")
        return [*common, group_skill]


# ---------------------------------------------------------------------------
# 运行记录与审核闭环对接
# ---------------------------------------------------------------------------

def run_and_persist(
    conn: sqlite3.Connection,
    technology_id: str,
    target_date: str | None = None,
    top_k: int = 5,
    config_id: str = "full",
    generation_mode: str = "rule",
) -> dict[str, Any]:
    """执行一次预测并落 emerging_runs；失败也留痕（status=failed）。"""
    run_id = f"RUN-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
    target = date.fromisoformat(target_date) if target_date else date.today()
    request = {"technology_id": technology_id, "target_date": target.isoformat(),
               "top_k": top_k, "config_id": config_id, "generation_mode": generation_mode}
    try:
        algorithm = EmergingJobAlgorithm(UnifiedRepository(conn))
        result = algorithm.run(technology_id, target, top_k=top_k, config_id=config_id,
                               provider=get_provider(generation_mode))
        conn.execute(
            "INSERT INTO emerging_runs (run_id, technology_id, status, request_json, result_json, completed_at)"
            " VALUES (?, ?, 'completed', ?, ?, datetime('now'))",
            (run_id, technology_id, json.dumps(request, ensure_ascii=False),
             json.dumps(result, ensure_ascii=False)),
        )
        conn.commit()
        return {"run_id": run_id, "status": "completed", "result": result}
    except Exception as e:  # noqa: BLE001 - 失败需留痕供排查
        conn.execute(
            "INSERT INTO emerging_runs (run_id, technology_id, status, request_json, error, completed_at)"
            " VALUES (?, ?, 'failed', ?, ?, datetime('now'))",
            (run_id, technology_id, json.dumps(request, ensure_ascii=False), f"{type(e).__name__}: {e}"),
        )
        conn.commit()
        raise


def submit_candidate(conn: sqlite3.Connection, run_id: str, candidate_id: str) -> int:
    """候选岗位五要素 → job_definitions（review_status=pending，对接审核闭环）。"""
    row = conn.execute("SELECT result_json FROM emerging_runs WHERE run_id = ?", (run_id,)).fetchone()
    if not row:
        raise KeyError(f"运行记录不存在: {run_id}")
    result = json.loads(row["result_json"])
    candidate = next((c for c in result.get("candidate_jobs", [])
                      if c["candidate_id"] == candidate_id), None)
    if candidate is None:
        raise KeyError(f"候选岗位不存在: {candidate_id}")
    cur = conn.execute(
        """
        INSERT INTO job_definitions
            (technology_id, job_type, job_name, core_duties, required_skills, bonus_skills,
             industry_scenarios, scores_json, evidence_json, generation_source, review_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'emerging', 'pending')
        """,
        (
            result["technology"]["technology_id"],
            candidate["job_type"],
            candidate["job_title"],
            "；".join(candidate["responsibilities"]),
            json.dumps(candidate["required_skills"], ensure_ascii=False),
            json.dumps(candidate["bonus_skills"], ensure_ascii=False),
            "；".join(candidate["application_scenarios"]),
            json.dumps(candidate["scores"], ensure_ascii=False),
            json.dumps(candidate["evidence"], ensure_ascii=False),
        ),
    )
    conn.commit()
    return cur.lastrowid
