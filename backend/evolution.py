"""阶段 5：新岗位定义与能力动态更新（交付案例）。

1. 新岗位定义：从聚类（新岗位候选）出发，LLM 生成五要素岗位定义
   （名称/核心职责/必备技能/加分技能/应用场景），无 Key 时降级为启发式拼装；
   生成结果一律 review_status='pending'——未审核不入正式表（阶段 4 规则）。
2. 能力动态更新：对既有岗位做快照 → 用更新后的 JD 重提取 → 快照差分，
   输出新增/删除/修改标注与更新说明（快照差分按项目三设计文档实现）。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from pipeline import llm
from pipeline.extract import compile_skills, extract_one

DEFINITION_SYSTEM_PROMPT = (
    "你是具身智能与新一代信息技术产业的岗位研究专家。"
    "请基于一个 JD 聚类（若干相似岗位的聚合）归纳出一个新岗位的标准化定义。"
    "只输出合法 JSON 对象，不要输出 Markdown，字段如下："
    '{"job_name": 岗位名称(简洁中文), "core_duties": 核心职责(3-5 条, 分号分隔), '
    '"required_skills": 必备技能(数组, 5-8 个), "bonus_skills": 加分技能(数组, 3-6 个), '
    '"industry_scenarios": 典型应用场景(2-3 条, 分号分隔)}'
)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_list(value: str | None) -> list[str]:
    """容错解析：JSON 数组或逗号分隔字符串（源库聚类为后者）。"""
    if not value:
        return []
    v = str(value).strip()
    if v.startswith("["):
        try:
            parsed = json.loads(v)
            return [str(x) for x in parsed] if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            pass
    return [x.strip() for x in v.replace("，", ",").split(",") if x.strip()]


# ---------------------------------------------------------------------------
# 新岗位定义
# ---------------------------------------------------------------------------

def generate_definition(conn: sqlite3.Connection, cluster_id: str) -> dict:
    """基于聚类生成五要素岗位定义（LLM；降级启发式），落 job_definitions 待审。"""
    row = conn.execute(
        """
        SELECT c.cluster_id, c.cluster_name, c.description, c.shared_skills,
               c.representative_titles, c.keywords, c.job_count,
               cc.primary_l1_code, cc.primary_l2_name
        FROM clusters c
        LEFT JOIN cluster_classifications cc ON c.cluster_id = cc.cluster_id
        WHERE c.cluster_id = ?
        """,
        (cluster_id,),
    ).fetchone()
    if not row:
        raise KeyError(f"聚类不存在: {cluster_id}")

    shared = _parse_list(row["shared_skills"])
    titles = _parse_list(row["representative_titles"])
    keywords = _parse_list(row["keywords"])

    llm_used = False
    definition = None
    if llm.is_available():
        user_prompt = (
            f"聚类名称：{row['cluster_name']}\n"
            f"聚类描述：{row['description'] or '无'}\n"
            f"聚合岗位数：{row['job_count']}\n"
            f"共享技能：{', '.join(shared)}\n"
            f"代表岗位标题：{', '.join(titles[:8])}\n"
            f"关键词：{', '.join(keywords)}\n"
            f"所属技术域：{row['primary_l1_code'] or '未知'} / {row['primary_l2_name'] or '未知'}"
        )
        definition = llm.chat_json(DEFINITION_SYSTEM_PROMPT, user_prompt)
        llm_used = definition is not None

    if not definition:
        # 降级：启发式拼装（全部来自真实聚类数据，无生成幻觉）
        bonus = [k for k in keywords if k not in shared][:6]
        scope = row["primary_l2_name"] or "该领域"
        definition = {
            "job_name": row["cluster_name"],
            "core_duties": (
                f"围绕{scope}方向开展专业工作；完成岗位相关的技术方案落地与交付；"
                "与团队协作推进项目迭代优化"
            ),
            "required_skills": shared[:8],
            "bonus_skills": bonus,
            "industry_scenarios": "；".join(titles[:3]) or "暂无",
        }

    required = definition.get("required_skills") or []
    bonus = definition.get("bonus_skills") or []
    cur = conn.execute(
        """
        INSERT INTO job_definitions
        (cluster_id, job_name, core_duties, required_skills, bonus_skills,
         industry_scenarios, generation_source, review_status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """,
        (
            cluster_id,
            definition.get("job_name") or row["cluster_name"],
            definition.get("core_duties") or "",
            json.dumps(required, ensure_ascii=False),
            json.dumps(bonus, ensure_ascii=False),
            definition.get("industry_scenarios") or "",
            "llm" if llm_used else "heuristic",
            _now(),
        ),
    )
    conn.commit()
    return {
        "definitionId": cur.lastrowid,
        "clusterId": cluster_id,
        "llmUsed": llm_used,
        "jobName": definition.get("job_name") or row["cluster_name"],
        "reviewStatus": "pending",
    }


def list_definitions(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM job_definitions ORDER BY definition_id DESC LIMIT ?", (limit,)
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for f in ("required_skills", "bonus_skills"):
            try:
                d[f] = json.loads(d[f] or "[]")
            except json.JSONDecodeError:
                d[f] = _parse_list(d[f])
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# 快照与差分（能力动态更新）
# ---------------------------------------------------------------------------

def _job_skill_payload(conn: sqlite3.Connection, job_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT s.skill_term, js.confidence, js.evidence, js.review_status, js.source
        FROM job_skills js JOIN skills s ON js.skill_id = s.skill_id
        WHERE js.job_id = ? ORDER BY s.skill_term
        """,
        (job_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def take_snapshot(conn: sqlite3.Connection, job_id: str, label: str | None = None) -> dict:
    """对岗位当前 job_skills 拍快照（payload 存 JSON，快照不可变）。"""
    job = conn.execute("SELECT title FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    if not job:
        raise KeyError(f"岗位不存在: {job_id}")
    skills = _job_skill_payload(conn, job_id)
    payload = json.dumps({"job_id": job_id, "title": job["title"], "skills": skills},
                         ensure_ascii=False)
    cur = conn.execute(
        "INSERT INTO snapshots (label, payload, created_at) VALUES (?, ?, ?)",
        (label or f"job:{job_id}", payload, _now()),
    )
    conn.commit()
    return {"snapshotId": cur.lastrowid, "jobId": job_id, "skillCount": len(skills),
            "label": label or f"job:{job_id}"}


def refresh_skills(conn: sqlite3.Connection, job_id: str, jd_text: str | None = None) -> dict:
    """用（更新后的）JD 文本重提取技能并替换该岗位图谱边 —— 能力动态更新入口。"""
    job = conn.execute("SELECT jd_text FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    if not job:
        raise KeyError(f"岗位不存在: {job_id}")
    text = jd_text or job["jd_text"]
    if not text or not text.strip():
        raise ValueError("JD 文本为空，无法重提取")

    records = compile_skills(conn)
    hits = extract_one(text, records)
    conn.execute("DELETE FROM job_skills WHERE job_id = ?", (job_id,))
    for h in hits:
        status = "approved" if h.get("evidence") else "pending"
        conn.execute(
            """
            INSERT INTO job_skills
            (job_id, skill_id, evidence, confidence, l4_type, source, review_status)
            VALUES (?, ?, ?, 0.95, ?, 'dictionary', ?)
            """,
            (job_id, h["skill_id"], h["evidence"], h["l4_type"], status),
        )
    conn.commit()
    return {"jobId": job_id, "skillCount": len(hits), "reextracted": True}


def diff_snapshots(conn: sqlite3.Connection, base_id: int, new_id: int) -> dict:
    """对比两次快照：新增/删除/修改标注 + 更新说明，写 snapshot_diffs 留痕。"""
    base = conn.execute("SELECT * FROM snapshots WHERE snapshot_id = ?", (base_id,)).fetchone()
    new = conn.execute("SELECT * FROM snapshots WHERE snapshot_id = ?", (new_id,)).fetchone()
    if not base or not new:
        raise KeyError("快照不存在")
    base_skills = {s["skill_term"]: s for s in json.loads(base["payload"])["skills"]}
    new_skills = {s["skill_term"]: s for s in json.loads(new["payload"])["skills"]}

    added = sorted(set(new_skills) - set(base_skills))
    removed = sorted(set(base_skills) - set(new_skills))
    modified = []
    for term in sorted(set(base_skills) & set(new_skills)):
        b, n = base_skills[term], new_skills[term]
        if abs((b["confidence"] or 0) - (n["confidence"] or 0)) > 1e-6 or \
           (b["evidence"] or "") != (n["evidence"] or ""):
            modified.append(term)

    job_id = json.loads(new["payload"]).get("job_id", "")
    rows = (
        [("added", t) for t in added]
        + [("removed", t) for t in removed]
        + [("modified", t) for t in modified]
    )
    for change_type, term in rows:
        skill_id = conn.execute(
            "SELECT skill_id FROM skills WHERE skill_term = ?", (term,)
        ).fetchone()
        conn.execute(
            """
            INSERT INTO snapshot_diffs
            (base_snapshot, new_snapshot, job_id, change_type, skill_id, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (base_id, new_id, job_id, change_type,
             skill_id["skill_id"] if skill_id else None,
             json.dumps({"skill_term": term}, ensure_ascii=False), _now()),
        )
    conn.commit()

    note_parts = []
    if added:
        note_parts.append(f"新增能力 {len(added)} 项（{'、'.join(added[:5])}"
                          f"{'等' if len(added) > 5 else ''}）")
    if removed:
        note_parts.append(f"移除能力 {len(removed)} 项（{'、'.join(removed[:5])}"
                          f"{'等' if len(removed) > 5 else ''}）")
    if modified:
        note_parts.append(f"置信度/证据更新 {len(modified)} 项")
    update_note = "；".join(note_parts) if note_parts else "能力结构无变化"

    return {
        "baseSnapshot": base_id,
        "newSnapshot": new_id,
        "jobId": job_id,
        "added": added,
        "removed": removed,
        "modified": modified,
        "updateNote": update_note,
    }


def list_snapshots(conn: sqlite3.Connection, job_id: str | None = None,
                   limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT snapshot_id, label, created_at, payload FROM snapshots "
        "ORDER BY snapshot_id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    out = []
    for r in rows:
        payload = json.loads(r["payload"])
        if job_id and payload.get("job_id") != job_id:
            continue
        out.append({
            "snapshotId": r["snapshot_id"],
            "label": r["label"],
            "jobId": payload.get("job_id"),
            "title": payload.get("title"),
            "skillCount": len(payload.get("skills", [])),
            "createdAt": r["created_at"],
        })
    return out
