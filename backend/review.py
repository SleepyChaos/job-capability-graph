"""阶段 4：幻觉防控与人工审核（审核状态机，参照项目三治理机制）。

机制要点（创新性主打）：
1. 证据溯源：每条图谱边（job_skills）带 JD 原文证据片段 evidence，可回溯；
2. 置信度门限：词典正则命中（确定性锚点，confidence 0.95）自动放行；
   置信度低于 AUTO_APPROVE_CONF 或 LLM 来源的结果一律 pending（未审核不入正式表）；
3. 审核闭环：审核决定写入 reviews 表留痕，同步更新目标 review_status。

状态机：pending --approve--> approved / pending --reject--> rejected
        approved / rejected 为终态（再次审核需新增记录，日志可追溯）。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

# 项目三口径：≥90% 可自动处理；80%–90% 人工审核；<80% 应重做（此处统一进待审）
AUTO_APPROVE_CONF = 0.90

# 审核目标类型 → （状态字段所在表, 主键列）
TARGET_TABLES = {
    "edge": ("job_skills", None),  # 复合主键，target_id 形如 "job_id|skill_id"
    "cluster": ("clusters", "cluster_id"),
    "definition": ("job_definitions", "definition_id"),
    "skill": ("skills", "skill_id"),
}


def decide_status(source: str, confidence: float, has_evidence: bool) -> str:
    """入库前状态判定：确定性锚点自动放行，其余待人工审核。"""
    if source == "dictionary" and confidence >= AUTO_APPROVE_CONF and has_evidence:
        return "approved"
    return "pending"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def summary(conn: sqlite3.Connection) -> dict:
    """审核看板统计：各队列待审数量 + 证据覆盖率 + 门限策略说明。"""
    pending_edges = conn.execute(
        "SELECT COUNT(*) AS n FROM job_skills WHERE review_status = 'pending'"
    ).fetchone()["n"]
    pending_clusters = conn.execute(
        "SELECT COUNT(*) AS n FROM clusters WHERE review_status = 'pending'"
    ).fetchone()["n"]
    pending_definitions = conn.execute(
        "SELECT COUNT(*) AS n FROM job_definitions WHERE review_status = 'pending'"
    ).fetchone()["n"]
    ev = conn.execute(
        "SELECT SUM(CASE WHEN evidence IS NOT NULL AND evidence != '' THEN 1 ELSE 0 END) AS with_ev, "
        "COUNT(*) AS total FROM job_skills"
    ).fetchone()
    decided = conn.execute(
        "SELECT COUNT(*) AS n FROM reviews"
    ).fetchone()["n"]
    approved_edges = conn.execute(
        "SELECT COUNT(*) AS n FROM job_skills WHERE review_status = 'approved'"
    ).fetchone()["n"]
    rejected_edges = conn.execute(
        "SELECT COUNT(*) AS n FROM job_skills WHERE review_status = 'rejected'"
    ).fetchone()["n"]
    return {
        "pending": {
            "edge": pending_edges,
            "cluster": pending_clusters,
            "definition": pending_definitions,
        },
        "edges": {
            "approved": approved_edges,
            "rejected": rejected_edges,
            "pending": pending_edges,
            "evidenceCovered": ev["with_ev"],
            "total": ev["total"],
            "evidenceCoverage": round((ev["with_ev"] or 0) / ev["total"], 4) if ev["total"] else 0,
        },
        "decidedTotal": decided,
        "policy": {
            "autoApproveConfidence": AUTO_APPROVE_CONF,
            "description": (
                f"词典正则命中（置信度 ≥{AUTO_APPROVE_CONF:.0%} 且有 JD 证据）自动放行；"
                "LLM 生成与低置信结果一律进入待审队列，未审核不入正式图谱。"
            ),
        },
    }


def queue(conn: sqlite3.Connection, target_type: str, limit: int = 50) -> list[dict]:
    """待审核队列（含证据/上下文，供人工裁决）。"""
    if target_type == "edge":
        rows = conn.execute(
            """
            SELECT js.job_id || '|' || js.skill_id AS target_id,
                   j.title AS job_title, s.skill_term, js.evidence,
                   js.confidence, js.source, js.created_at
            FROM job_skills js
            JOIN jobs j ON js.job_id = j.job_id
            JOIN skills s ON js.skill_id = s.skill_id
            WHERE js.review_status = 'pending'
            ORDER BY js.confidence DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    if target_type == "cluster":
        rows = conn.execute(
            """
            SELECT c.cluster_id AS target_id, c.cluster_name, c.description,
                   c.shared_skills, c.representative_titles, c.job_count,
                   c.name_source, c.created_at,
                   cc.primary_l1_code, cc.primary_l2_name
            FROM clusters c
            LEFT JOIN cluster_classifications cc ON c.cluster_id = cc.cluster_id
            WHERE c.review_status = 'pending'
            ORDER BY c.job_count DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    if target_type == "definition":
        rows = conn.execute(
            """
            SELECT definition_id AS target_id, cluster_id, technology_id, job_type,
                   job_name, core_duties,
                   required_skills, bonus_skills, industry_scenarios,
                   scores_json, evidence_json, generation_source, created_at
            FROM job_definitions WHERE review_status = 'pending'
            ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    raise ValueError(f"未知审核目标类型: {target_type}")


def decide(
    conn: sqlite3.Connection,
    target_type: str,
    target_id: str,
    action: str,
    reviewer: str = "reviewer",
    comment: str = "",
) -> dict:
    """审核裁决：更新目标状态 + 写 reviews 留痕。action: approve / reject。"""
    if target_type not in TARGET_TABLES:
        raise ValueError(f"未知审核目标类型: {target_type}")
    if action not in ("approve", "reject"):
        raise ValueError(f"未知审核动作: {action}")
    new_status = "approved" if action == "approve" else "rejected"

    table, pk = TARGET_TABLES[target_type]
    if target_type == "edge":
        parts = target_id.split("|")
        if len(parts) != 2:
            raise ValueError("edge 的 target_id 格式应为 job_id|skill_id")
        job_id, skill_id = parts[0], int(parts[1])
        cur = conn.execute(
            "UPDATE job_skills SET review_status = ? WHERE job_id = ? AND skill_id = ?",
            (new_status, job_id, skill_id),
        )
    else:
        cur = conn.execute(
            f"UPDATE {table} SET review_status = ? WHERE {pk} = ?",
            (new_status, target_id),
        )
    if cur.rowcount == 0:
        raise KeyError(f"审核目标不存在: {target_type}/{target_id}")

    conn.execute(
        """
        INSERT INTO reviews (target_type, target_id, action, reviewer, comment, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (target_type, str(target_id), action, reviewer, comment, _now()),
    )
    conn.commit()
    return {"targetType": target_type, "targetId": target_id, "status": new_status}


def log(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT review_id, target_type, target_id, action, reviewer, comment, created_at "
        "FROM reviews ORDER BY review_id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
