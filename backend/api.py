"""统一后端 API（阶段 2）：FastAPI 服务，读取统一库 unified.db（单一事实源）。

路由骨架参照项目三 main.py 的 REST 风格；本阶段提供图谱/聚类/岗位/统计接口。
运行（项目根目录）：
  .venv/bin/uvicorn backend.api:app --port 8000 --reload
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DB_PATH = Path(__file__).resolve().parent.parent / "db" / "unified.db"

app = FastAPI(title="岗位能力图谱统一 API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# L1 域 → 前端分类键（沿用项目一 category 口径；T1–T7 归入 embodied 具身智能域）
L1_TO_CATEGORY = {"AI": "ai", "BD": "bigdata", "IOT": "iot", "IS": "smart"}
CATEGORY_DEFAULT = "embodied"  # T1–T7 等具身智能域（迁移主体数据）

# 具身七子域分层配额（系统专精具身智能：图谱默认视图按 T 域配额选点，
# 避免“技能数头部”口径被 T1 算法类岗位垄断导致其余子域缺簇）
EMBODIED_QUOTAS = {"T1": 80, "T7": 40, "T3": 30, "T6": 15, "T4": 10, "T5": 8, "T2": 7}

# 技能类型启发式（项目一 type 口径：hard/soft/domain/tool）
TOOL_HINTS = ("docker", "kubernetes", "k8s", "git", "linux", "mysql", "redis", "kafka",
              "hadoop", "spark", "flink", "tableau", "opencv", "cuda", "onnx", "vllm",
              "langchain", "tensorflow", "pytorch", "paddle", "mindspore", "scikit")
DOMAIN_HINTS = ("治理", "合规", "安全", "画像", "分析", "建模", "标准", "场景", "孪生")
SOFT_HINTS = ("沟通", "管理", "协作", "规划", "培训")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def derive_level(experience: str) -> str:
    """从经验要求推导岗位级别：3年以下初级 / 3-5 中级 / 5 年以上高级。"""
    exp = experience or ""
    if "以上" in exp:
        return "senior"
    if "以下" in exp or "以内" in exp:
        return "junior"
    m = re.search(r"(\d+)", exp)
    if not m:
        return "mid"
    n = int(m.group(1))
    if n < 3:
        return "junior"
    if n < 5:
        return "mid"
    return "senior"


def skill_type_of(term: str) -> str:
    t = term.lower()
    if any(h in t for h in TOOL_HINTS):
        return "tool"
    if any(h in term for h in SOFT_HINTS):
        return "soft"
    if any(h in term for h in DOMAIN_HINTS):
        return "domain"
    return "hard"


def parse_list_field(value: str | None) -> list:
    """容错解析列表字段：JSON 数组或逗号分隔字符串（源库聚类为后者）。"""
    if not value:
        return []
    v = value.strip()
    if v.startswith("["):
        try:
            parsed = json.loads(v)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            pass
    return [x.strip() for x in re.split(r"[,，]", v) if x.strip()]


def job_row_to_node(r: sqlite3.Row, max_salary: float) -> dict:
    category = L1_TO_CATEGORY.get(r["l1_code"] or "", CATEGORY_DEFAULT)
    salary_max = r["salary_max"] or 0
    demand = int(50 + 49 * (salary_max / max_salary)) if max_salary else 60
    return {
        "id": r["job_id"],
        "name": (r["title"] or "").split("\n")[0].strip(),  # 源数据个别 title 含多行，取首行
        "category": category,
        "l1": r["l1_code"] or "",  # 主导 L1 域（T1–T7 具身子域 / AI / BD / IOT / IS）
        "level": derive_level(r["experience"]),
        "skills": json.loads(r["skills_json"] or "[]"),
        "demand": min(demand, 99),
        "salary": r["salary_text"] or "",
        "description": (r["jd_text"] or "")[:80],
        "company": r["company"] or "",
        "city": r["city"] or "",
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "db": str(DB_PATH)}


@app.get("/api/stats")
def stats():
    conn = get_conn()
    row = conn.execute(
        """
        SELECT (SELECT COUNT(*) FROM jobs) AS jobs,
               (SELECT COUNT(*) FROM skills) AS skills,
               (SELECT COUNT(*) FROM job_skills) AS edges,
               (SELECT COUNT(*) FROM clusters) AS clusters,
               (SELECT COUNT(*) FROM job_cluster_map) AS clustered_jobs
        """
    ).fetchone()
    l1_dist = [
        {
            "code": r["l1_code"],
            "name": r["l1_name"],
            "clusters": conn.execute(
                "SELECT COUNT(*) AS n FROM cluster_classifications WHERE primary_l1_code = ?",
                (r["l1_code"],),
            ).fetchone()["n"],
        }
        for r in conn.execute("SELECT l1_code, l1_name FROM domains ORDER BY l1_code").fetchall()
    ]
    meta = {
        r["key"]: r["value"]
        for r in conn.execute("SELECT key, value FROM pipeline_meta").fetchall()
    }
    conn.close()
    return {
        "jobs": row["jobs"],
        "skills": row["skills"],
        "edges": row["edges"],
        "clusters": row["clusters"],
        "clusteredJobs": row["clustered_jobs"],
        "l1Distribution": l1_dist,
        "pipeline": meta,
    }


@app.get("/api/graph")
def graph(
    level: str = Query("all", description="junior/mid/senior/all"),
    category: str = Query("all", description="ai/bigdata/iot/smart/embodied/all"),
    limit_jobs: int = Query(250, le=800, description="岗位节点上限（真实体量下按技能数取头部）"),
    limit_skills: int = Query(120, le=400),
):
    """岗位-技能二部图数据（与前端 JobNode/SkillNode 结构对齐）。

    阶段 2.5 适配：岗位数 6,793 超出前端 Canvas 渲染能力，岗位侧按技能数取头部
    limit_jobs 个节点，技能侧按需求数取 Top-N；筛选下推到 SQL。
    """
    conn = get_conn()
    # 1) 岗位基础信息 + 技能数（一次 JOIN 聚合，替代逐行相关子查询：
    #    原实现对 6,793 个岗位逐行执行 3 个相关子查询，接口耗时 ~25s）
    jobs = conn.execute(
        """
        SELECT j.job_id, j.title, j.company, j.city, j.experience, j.salary_text,
               j.salary_max, substr(j.jd_text, 1, 80) AS jd_text,
               cnt.skill_cnt
        FROM jobs j
        JOIN (
            SELECT job_id, COUNT(*) AS skill_cnt FROM job_skills
            WHERE review_status = 'approved' GROUP BY job_id
        ) cnt ON cnt.job_id = j.job_id
        """
    ).fetchall()
    # 2) 主导 L1 域（一次窗口聚合）
    dom_map = {
        r["job_id"]: r["l1_code"]
        for r in conn.execute(
            """
            SELECT job_id, l1_code FROM (
                SELECT js.job_id, s.l1_code, COUNT(*) AS c,
                       ROW_NUMBER() OVER (PARTITION BY js.job_id ORDER BY COUNT(*) DESC) AS rn
                FROM job_skills js JOIN skills s ON js.skill_id = s.skill_id
                WHERE s.l1_code IS NOT NULL
                GROUP BY js.job_id, s.l1_code
            ) WHERE rn = 1
            """
        ).fetchall()
    }
    max_salary = max((r["salary_max"] or 0) for r in jobs) if jobs else 0

    job_nodes: list[dict] = []
    for r in jobs:
        l1_code = dom_map.get(r["job_id"]) or ""
        if level != "all" and derive_level(r["experience"]) != level:
            continue
        job_nodes.append({
            "job_id": r["job_id"],
            "l1_code": l1_code,
            "l1": l1_code,
            "category": L1_TO_CATEGORY.get(l1_code, CATEGORY_DEFAULT),
            "title": r["title"],
            "company": r["company"],
            "city": r["city"],
            "experience": r["experience"],
            "salary_text": r["salary_text"],
            "salary_max": r["salary_max"],
            "jd_text": r["jd_text"],
            "skills_json": "[]",
            "_skill_cnt": r["skill_cnt"],
        })

    if category in ("all", "embodied"):
        # 具身七子域分层配额：每个 T 域内按技能数取头部，保证七簇齐全；
        # 默认视图专精具身智能，不混入非具身岗位（筛选非具身分类时另走下方分支）
        scale = limit_jobs / sum(EMBODIED_QUOTAS.values())
        by_l1: dict[str, list[dict]] = {}
        for n in job_nodes:
            if n["l1"] in EMBODIED_QUOTAS:
                by_l1.setdefault(n["l1"], []).append(n)
        selected: list[dict] = []
        for l1_code, quota in EMBODIED_QUOTAS.items():
            group = sorted(by_l1.get(l1_code, []), key=lambda n: n["_skill_cnt"], reverse=True)
            selected.extend(group[: max(1, round(quota * scale))])
        job_nodes = selected[:limit_jobs]
    else:
        # 指定非具身分类：维持原有“技能数头部”口径
        job_nodes = [n for n in job_nodes if n["category"] == category]
        job_nodes.sort(key=lambda n: n["_skill_cnt"], reverse=True)
        job_nodes = job_nodes[:limit_jobs]

    # 3) 选中岗位技能明细（一次 IN 查询，Python 侧取每岗位 Top-8）
    job_ids = {n["job_id"] for n in job_nodes}
    if job_ids:
        ph = ",".join("?" * len(job_ids))
        skills_by_job: dict[str, list[str]] = {}
        for r in conn.execute(
            f"SELECT js.job_id, s.skill_term FROM job_skills js "
            f"JOIN skills s ON js.skill_id = s.skill_id "
            f"WHERE js.review_status = 'approved' AND js.job_id IN ({ph}) "
            f"ORDER BY js.job_id, js.confidence DESC",
            tuple(job_ids),
        ).fetchall():
            lst = skills_by_job.setdefault(r["job_id"], [])
            if len(lst) < 8:
                lst.append(r["skill_term"])
        for n in job_nodes:
            n["skills_json"] = json.dumps(skills_by_job.get(n["job_id"], []), ensure_ascii=False)

    # 4) 转标准节点结构（与前端 JobNode 对齐）
    job_nodes = [job_row_to_node(n, max_salary) for n in job_nodes]

    job_ids = {n["id"] for n in job_nodes}
    # 技能节点：按过滤后岗位的需求数加权
    placeholders = ",".join("?" * len(job_ids)) if job_ids else "''"
    skill_rows = conn.execute(
        f"""
        SELECT s.skill_id, s.skill_term, s.l1_code, COUNT(DISTINCT js.job_id) AS job_cnt
        FROM job_skills js JOIN skills s ON js.skill_id = s.skill_id
        WHERE js.review_status = 'approved' AND js.job_id IN ({placeholders})
        GROUP BY s.skill_id
        ORDER BY job_cnt DESC
        LIMIT ?
        """,
        (*job_ids, limit_skills) if job_ids else (limit_skills,),
    ).fetchall() if job_ids else []

    # 技能-岗位关联
    skill_ids = [r["skill_id"] for r in skill_rows]
    skill_jobs: dict[int, list[str]] = {}
    if skill_ids and job_ids:
        ph_s = ",".join("?" * len(skill_ids))
        for r in conn.execute(
            f"SELECT skill_id, job_id FROM job_skills "
            f"WHERE review_status = 'approved' AND skill_id IN ({ph_s})",
            skill_ids,
        ).fetchall():
            if r["job_id"] in job_ids:
                skill_jobs.setdefault(r["skill_id"], []).append(r["job_id"])

    max_cnt = max((r["job_cnt"] for r in skill_rows), default=1)
    skill_nodes = [
        {
            "id": f"s{r['skill_id']}",
            "name": r["skill_term"],
            "type": skill_type_of(r["skill_term"]),
            "jobs": skill_jobs.get(r["skill_id"], []),
            "weight": int(40 + 60 * (r["job_cnt"] / max_cnt)),
            "category": L1_TO_CATEGORY.get(r["l1_code"] or "", CATEGORY_DEFAULT),
            "jobCount": r["job_cnt"],
        }
        for r in skill_rows
    ]
    conn.close()
    return {"jobs": job_nodes, "skills": skill_nodes, "totalJobs": len(job_nodes)}


@app.get("/api/heatmap")
def heatmap(days: int = Query(180, ge=1, le=365)):
    """技能需求热力图（L2 粒度，仅 T1–T7 具身七子域）。

    行 = T 域下的 L2 技能类目，列 = 初级/中级/高级职级；
    热力值 = 活跃岗位数：最近 days 天内收录（collect_time ≥ cutoff）或
    无收录时间（视为近期收录）的岗位中，命中该类目下任一技能（approved）
    的岗位去重计数——技能越频繁出现在活跃岗位 JD 中颜色越深。
    """
    conn = get_conn()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute(
        """
        SELECT DISTINCT j.job_id, j.experience, s.l2_id, l2.l1_code, l2.l2_name
        FROM job_skills js
        JOIN jobs j ON j.job_id = js.job_id
        JOIN skills s ON s.skill_id = js.skill_id
        JOIN l2_categories l2 ON l2.l2_id = s.l2_id
        WHERE js.review_status = 'approved'
          AND l2.l1_code LIKE 'T%'
          AND (j.collect_time >= ? OR j.collect_time IS NULL OR j.collect_time = '')
        """,
        (cutoff,),
    ).fetchall()
    cells: dict[int, dict[str, int]] = {}
    meta: dict[int, dict] = {}
    for r in rows:
        lv = derive_level(r["experience"])
        c = cells.setdefault(r["l2_id"], {"junior": 0, "mid": 0, "senior": 0})
        c[lv] += 1
        meta.setdefault(r["l2_id"], {"l1_code": r["l1_code"], "l2_name": r["l2_name"]})
    result = [
        {"l2_id": k, "l1_code": meta[k]["l1_code"], "l2_name": meta[k]["l2_name"], "cells": v}
        for k, v in cells.items()
    ]
    result.sort(key=lambda x: (x["l1_code"], x["l2_name"]))
    total = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE collect_time >= ? OR collect_time IS NULL OR collect_time = ''",
        (cutoff,),
    ).fetchone()[0]
    conn.close()
    return {"days": days, "total_jobs": total, "rows": result}


@app.get("/api/clusters")
def clusters(
    min_jobs: int = Query(1),
    l1: str = Query("all"),
    limit: int = Query(200, le=2000),
    offset: int = 0,
):
    """聚类列表（新岗位发现页数据源），带分类与成员岗位；阶段 2.5 起支持分页。"""
    conn = get_conn()
    where = "WHERE c.job_count >= ?"
    params: list = [min_jobs]
    if l1 != "all":
        where += " AND cc.primary_l1_code = ?"
        params.append(l1)
    total = conn.execute(
        f"""
        SELECT COUNT(*) AS n FROM clusters c
        LEFT JOIN cluster_classifications cc ON c.cluster_id = cc.cluster_id {where}
        """,
        params,
    ).fetchone()["n"]
    rows = conn.execute(
        f"""
        SELECT c.cluster_id, c.cluster_name, c.description, c.shared_skills,
               c.representative_titles, c.keywords, c.job_count, c.name_source,
               c.review_status, c.clustered_at,
               cc.primary_l1_code, cc.primary_l2_name
        FROM clusters c
        LEFT JOIN cluster_classifications cc ON c.cluster_id = cc.cluster_id
        {where}
        ORDER BY c.job_count DESC
        LIMIT ? OFFSET ?
        """,
        (*params, limit, offset),
    ).fetchall()

    # 仅加载当页聚类的成员岗位
    page_ids = [r["cluster_id"] for r in rows]
    members: dict[str, list[dict]] = {}
    if page_ids:
        ph = ",".join("?" * len(page_ids))
        for r in conn.execute(
            f"SELECT m.cluster_id, m.job_id, j.title, j.company, j.city, j.salary_text "
            f"FROM job_cluster_map m JOIN jobs j ON m.job_id = j.job_id "
            f"WHERE m.cluster_id IN ({ph})",
            page_ids,
        ).fetchall():
            members.setdefault(r["cluster_id"], []).append(
                {"id": r["job_id"], "title": r["title"], "company": r["company"],
                 "city": r["city"], "salary": r["salary_text"]}
            )
    conn.close()

    result = []
    for r in rows:
        result.append({
            "id": r["cluster_id"],
            "name": r["cluster_name"],
            "description": r["description"],
            "sharedSkills": parse_list_field(r["shared_skills"]),
            "representativeTitles": parse_list_field(r["representative_titles"]),
            "keywords": parse_list_field(r["keywords"]),
            "jobCount": r["job_count"],
            "nameSource": r["name_source"],
            "reviewStatus": r["review_status"],
            "clusteredAt": r["clustered_at"],
            "l1Code": r["primary_l1_code"] or "",
            "l2Name": r["primary_l2_name"] or "",
            "members": members.get(r["cluster_id"], []),
        })
    return {"clusters": result, "total": total}


@app.get("/api/jobs")
def list_jobs(limit: int = Query(50, le=500), offset: int = 0):
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) AS c FROM jobs").fetchone()["c"]
    rows = conn.execute(
        "SELECT job_id, title, company, city, salary_text, experience, education, collect_time "
        "FROM jobs ORDER BY job_id LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    conn.close()
    return {"total": total, "jobs": [dict(r) for r in rows]}


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: str):
    conn = get_conn()
    r = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    if not r:
        conn.close()
        return {"error": "not found"}
    skills = conn.execute(
        "SELECT s.skill_term, js.evidence, js.confidence, js.review_status "
        "FROM job_skills js JOIN skills s ON js.skill_id = s.skill_id WHERE js.job_id = ?",
        (job_id,),
    ).fetchall()
    conn.close()
    return {
        "job": dict(r),
        "skills": [dict(s) for s in skills],
    }


# -------------------------------------------------------------------------
# 阶段 3：简历解析与人岗匹配
# 解析管线 pipeline/resume_parse.py（pypdf + 词典正则 + LLM 降级）；
# 匹配引擎 backend/matching.py（移植项目三 vectorization.py 混合匹配）
# -------------------------------------------------------------------------
from backend.matching import MatchingEngine  # noqa: E402
from pipeline import resume_parse  # noqa: E402


def _resume_skill_rows(conn: sqlite3.Connection, resume_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT s.skill_term, s.l1_code, rs.confidence, rs.source
        FROM resume_skills rs JOIN skills s ON rs.skill_id = s.skill_id
        WHERE rs.resume_id = ? ORDER BY rs.confidence DESC
        """,
        (resume_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/resumes")
def list_resumes(limit: int = Query(50, le=500)):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT r.resume_id, r.name, r.title, r.file_name, r.created_at,
               (SELECT COUNT(*) FROM resume_skills rs WHERE rs.resume_id = r.resume_id) AS skill_count
        FROM resumes r ORDER BY r.created_at DESC, r.resume_id LIMIT ?
        """,
        (limit,),
    ).fetchall()
    total = conn.execute("SELECT COUNT(*) AS c FROM resumes").fetchone()["c"]
    conn.close()
    return {"total": total, "resumes": [dict(r) for r in rows]}


@app.post("/api/resumes/upload")
async def upload_resume(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
):
    """上传简历：PDF/TXT 文件或纯文本。解析 → 提取技能 → 落库，返回提取结果。"""
    conn = get_conn()
    try:
        try:
            if file is not None and file.filename:
                data = await file.read()
                if file.filename.lower().endswith(".pdf"):
                    raw_text = resume_parse.pdf_to_text(data)
                    if not raw_text:
                        raise HTTPException(400, "PDF 未提取到文本（可能为扫描件）")
                else:
                    raw_text = data.decode("utf-8", errors="ignore")
                result = resume_parse.parse_resume(conn, raw_text, file_name=file.filename)
            elif text:
                result = resume_parse.parse_resume(conn, text)
            else:
                raise HTTPException(400, "请上传文件或提供简历文本")
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {
            "resume_id": result["resume_id"],
            "name": result["name"],
            "title": result["title"],
            "llmUsed": result["llm_used"],
            "skills": _resume_skill_rows(conn, result["resume_id"]),
        }
    finally:
        conn.close()


@app.get("/api/resumes/{resume_id}")
def resume_detail(resume_id: str):
    conn = get_conn()
    r = conn.execute(
        "SELECT resume_id, name, title, file_name, skills_json, raw_text, created_at "
        "FROM resumes WHERE resume_id = ?",
        (resume_id,),
    ).fetchone()
    if not r:
        conn.close()
        raise HTTPException(404, "简历不存在")
    skills = _resume_skill_rows(conn, resume_id)
    conn.close()
    return {"resume": dict(r), "skills": skills}


@app.get("/api/resumes/{resume_id}/match")
def match_resume(
    resume_id: str,
    top_n: int = Query(10, ge=1, le=50),
    l1: str | None = Query(default=None, description="限定候选岗位 L1 域（如 T1）"),
):
    """人岗匹配：返回 Top N 岗位 + 各分量得分 + 技能差距清单。"""
    conn = get_conn()
    r = conn.execute("SELECT title FROM resumes WHERE resume_id = ?", (resume_id,)).fetchone()
    if not r:
        conn.close()
        raise HTTPException(404, "简历不存在")
    engine = MatchingEngine(conn)
    result = engine.match(resume_id, top_n=top_n, l1_filter=l1, resume_title=r["title"] or None)
    conn.close()
    return result


# -------------------------------------------------------------------------
# 阶段 4：幻觉防控与人工审核
# 状态机与策略见 backend/review.py（证据溯源 + 置信度门限 + 未审核不入正式表）
# -------------------------------------------------------------------------
from backend import review as review_mod  # noqa: E402


class ReviewDecision(BaseModel):
    targetType: str  # edge / cluster / definition
    targetId: str
    action: str  # approve / reject
    reviewer: str = "reviewer"
    comment: str = ""


@app.get("/api/review/summary")
def review_summary():
    conn = get_conn()
    result = review_mod.summary(conn)
    conn.close()
    return result


@app.get("/api/review/queue")
def review_queue(
    target_type: str = Query("cluster", description="edge/cluster/definition"),
    limit: int = Query(50, le=200),
):
    conn = get_conn()
    try:
        items = review_mod.queue(conn, target_type, limit)
    except ValueError as e:
        conn.close()
        raise HTTPException(400, str(e))
    conn.close()
    return {"targetType": target_type, "items": items}


@app.post("/api/review/decide")
def review_decide(body: ReviewDecision):
    conn = get_conn()
    try:
        result = review_mod.decide(
            conn, body.targetType, body.targetId, body.action,
            reviewer=body.reviewer, comment=body.comment,
        )
    except ValueError as e:
        conn.close()
        raise HTTPException(400, str(e))
    except KeyError as e:
        conn.close()
        raise HTTPException(404, str(e))
    conn.close()
    return result


@app.get("/api/review/log")
def review_log(limit: int = Query(50, le=500)):
    conn = get_conn()
    items = review_mod.log(conn, limit)
    conn.close()
    return {"items": items}


# -------------------------------------------------------------------------
# 阶段 5：新岗位定义与能力动态更新（交付案例）
# 五要素定义生成 + 快照差分，见 backend/evolution.py
# -------------------------------------------------------------------------
from backend import evolution as evolution_mod  # noqa: E402


class DefinitionRequest(BaseModel):
    clusterId: str


class SnapshotRequest(BaseModel):
    jobId: str
    label: str | None = None


class RefreshRequest(BaseModel):
    jobId: str
    jdText: str | None = None


@app.get("/api/definitions")
def definitions(limit: int = Query(50, le=200)):
    conn = get_conn()
    items = evolution_mod.list_definitions(conn, limit)
    conn.close()
    return {"items": items}


@app.post("/api/definitions/generate")
def generate_definition(body: DefinitionRequest):
    conn = get_conn()
    try:
        result = evolution_mod.generate_definition(conn, body.clusterId)
    except KeyError as e:
        conn.close()
        raise HTTPException(404, str(e))
    conn.close()
    return result


@app.get("/api/evolution/snapshots")
def snapshots(job_id: str | None = Query(default=None), limit: int = Query(50, le=200)):
    conn = get_conn()
    items = evolution_mod.list_snapshots(conn, job_id, limit)
    conn.close()
    return {"items": items}


@app.post("/api/evolution/snapshot")
def create_snapshot(body: SnapshotRequest):
    conn = get_conn()
    try:
        result = evolution_mod.take_snapshot(conn, body.jobId, body.label)
    except KeyError as e:
        conn.close()
        raise HTTPException(404, str(e))
    conn.close()
    return result


@app.post("/api/evolution/refresh")
def refresh_job_skills(body: RefreshRequest):
    """用更新后的 JD 文本重提取技能并替换图谱边（能力动态更新）。"""
    conn = get_conn()
    try:
        result = evolution_mod.refresh_skills(conn, body.jobId, body.jdText)
    except KeyError as e:
        conn.close()
        raise HTTPException(404, str(e))
    except ValueError as e:
        conn.close()
        raise HTTPException(400, str(e))
    conn.close()
    return result


@app.get("/api/evolution/diff")
def evolution_diff(base: int = Query(...), new: int = Query(...)):
    conn = get_conn()
    try:
        result = evolution_mod.diff_snapshots(conn, base, new)
    except KeyError as e:
        conn.close()
        raise HTTPException(404, str(e))
    conn.close()
    return result


# -------------------------------------------------------------------------
# 阶段 6：技术演化驱动的新兴岗位发现（移植自 embodied-job-evolution-lab）
# 引擎见 pipeline/emerging.py；候选岗位提交后进入 governance 审核闭环
# -------------------------------------------------------------------------
from pipeline import emerging as emerging_mod  # noqa: E402


class EmergingRunRequest(BaseModel):
    technologyId: str
    targetDate: str | None = None
    topK: int = 5
    configId: str = "full"  # full / no_maturity（消融）
    generationMode: str = "rule"  # rule / mock / llm


class EmergingSubmitRequest(BaseModel):
    runId: str
    candidateId: str


@app.get("/api/emerging/technologies/search")
def emerging_tech_search(q: str = Query(min_length=1, max_length=100)):
    conn = get_conn()
    items = emerging_mod.UnifiedRepository(conn).search_technologies(q)
    conn.close()
    return {"query": q, "items": items}


@app.post("/api/emerging/run")
def emerging_run(body: EmergingRunRequest):
    conn = get_conn()
    try:
        payload = emerging_mod.run_and_persist(
            conn, body.technologyId, target_date=body.targetDate,
            top_k=body.topK, config_id=body.configId,
            generation_mode=body.generationMode,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    finally:
        conn.close()
    return payload


@app.get("/api/emerging/runs")
def emerging_runs(limit: int = Query(20, ge=1, le=100)):
    conn = get_conn()
    rows = conn.execute(
        "SELECT run_id, technology_id, status, request_json, error, created_at, completed_at"
        " FROM emerging_runs ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return {"items": [dict(r) for r in rows]}


@app.get("/api/emerging/runs/{run_id}")
def emerging_run_detail(run_id: str):
    conn = get_conn()
    r = conn.execute("SELECT * FROM emerging_runs WHERE run_id = ?", (run_id,)).fetchone()
    conn.close()
    if not r:
        raise HTTPException(404, "运行记录不存在")
    row = dict(r)
    row["result"] = json.loads(row.pop("result_json")) if row.get("result_json") else None
    return row


@app.post("/api/emerging/submit")
def emerging_submit(body: EmergingSubmitRequest):
    """候选岗位五要素提交审核：写 job_definitions（pending），对接 governance 队列。"""
    conn = get_conn()
    try:
        definition_id = emerging_mod.submit_candidate(conn, body.runId, body.candidateId)
    except KeyError as e:
        conn.close()
        raise HTTPException(404, str(e))
    conn.close()
    return {"definitionId": definition_id, "reviewStatus": "pending"}


# -------------------------------------------------------------------------
# 设置：LLM 接入配置（设置页；Key 掩码返回，持久化到项目根 .env）
# -------------------------------------------------------------------------
from pipeline import config as pipeline_config  # noqa: E402
from pipeline import llm as pipeline_llm  # noqa: E402


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "***"
    return f"{key[:3]}***{key[-2:]}"


class LlmSettingsRequest(BaseModel):
    apiKey: str | None = None  # 空串/None 表示不修改；传空串且 clear=True 时清空
    baseUrl: str | None = None
    model: str | None = None
    clear: bool = False


@app.get("/api/settings/llm")
def llm_settings():
    return {
        "configured": pipeline_llm.is_available(),
        "keyMasked": _mask_key(pipeline_config.LLM_API_KEY),
        "baseUrl": pipeline_config.LLM_BASE_URL,
        "model": pipeline_config.LLM_MODEL,
    }


@app.post("/api/settings/llm")
def llm_settings_save(body: LlmSettingsRequest):
    """保存 LLM 配置：内存立即生效 + 回写 .env（不入代码库）。"""
    api_key = "" if body.clear else body.apiKey
    pipeline_config.apply_llm_overrides(
        api_key=api_key, base_url=body.baseUrl, model=body.model
    )
    updates: dict[str, str] = {}
    if api_key is not None:
        updates["OPENAI_API_KEY"] = api_key
    if body.baseUrl:
        updates["OPENAI_BASE_URL"] = body.baseUrl
    if body.model:
        updates["LLM_MODEL"] = body.model
    if updates:
        pipeline_config.persist_env(**updates)
    return {"saved": True, **llm_settings()}


@app.post("/api/settings/llm/test")
def llm_settings_test():
    """连接测试：真实调用一次 chat/completions（短提示，低消耗）。"""
    if not pipeline_llm.is_available():
        return {"ok": False, "error": "未配置 API Key"}
    text = pipeline_llm.chat(
        [{"role": "user", "content": "请用两个字回复：正常"}], temperature=0.1, timeout=20
    )
    if text is None:
        return {"ok": False, "error": "调用失败：请检查 Key/网络/接口地址"}
    return {"ok": True, "reply": text.strip()[:40], "model": pipeline_config.LLM_MODEL}
