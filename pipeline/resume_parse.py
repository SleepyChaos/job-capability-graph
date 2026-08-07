"""简历解析（阶段 3）：PDF/文本 → 结构化字段 + 技能提取写入 resumes/resume_skills。

复用来源（《开发文档.md》阶段 3 / 《模块复用分析.md》模块 5）：
1. PDF 解析：替换项目二 Coze SDK 方案为开源 pypdf（标准库 + pypdf）
2. 技能提取：复用 extract.py 的词典正则引擎（统一库 skills 本体，带证据溯源）
3. 结构化提取：提示词改编自项目二 prompts.ts 的 extractResumePrompt，
   LLM 走 pipeline/llm.py 的 OpenAI 兼容接口；未配置 Key 时自动降级为纯词典方案
"""
from __future__ import annotations

import argparse
import io
import json
import re
import uuid
from pathlib import Path

from . import db, llm
from .extract import compile_skills, extract_one, normalize_text

# 提示词改编自项目二 src/lib/prompts.ts extractResumePrompt（14 组 prompt 之一）
RESUME_SYSTEM_PROMPT = (
    "你是一位具身智能与新一代信息技术领域的招聘顾问，"
    "擅长从简历中提取候选人的关键匹配字段。"
)

RESUME_USER_TEMPLATE = """请从以下简历或求职描述中提取关键匹配字段。输出必须是严格的 JSON，不要包含任何解释性文字。

字段说明：
- name: 候选人姓名（字符串，无法识别则省略）
- title: 当前/目标职位头衔（字符串，无法识别则省略）
- skills: 技术技能关键词数组（如 ["强化学习", "ROS", "激光雷达", "PyTorch"]）
- cities: 期望工作城市数组
- directions: 发展方向偏好数组（如 ["算法", "感知", "控制", "硬件", "产品"]）
- other: 其他关键偏好或信息（字符串，无则省略）

简历/描述：
\"\"\"
{resume_text}
\"\"\"

请输出 JSON："""


def pdf_to_text(file_bytes: bytes) -> str:
    """PDF 字节流 → 纯文本（pypdf；替换项目二的 Coze FetchClient 方案）。"""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(file_bytes))
    parts = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(parts).strip()


def _map_term_to_skill(term: str, term_index: dict[str, int]) -> int | None:
    """LLM 提取的技能词 → 统一本体 skill_id（归一化后精确匹配，匹配不上不入正式表）。"""
    norm = normalize_text(term)
    return term_index.get(norm)


def build_term_index(conn) -> dict[str, int]:
    """归一化技能词 → skill_id 索引，供 LLM 结果映射本体。"""
    return {normalize_text(s["skill_term"]): s["skill_id"] for s in db.load_skills(conn)}


def extract_structured(raw_text: str) -> dict | None:
    """LLM 结构化提取（OpenAI 兼容接口）；未配置/失败返回 None（调用方降级）。"""
    if not llm.is_available():
        return None
    # 超长简历截断，控制 token 消耗
    truncated = raw_text[:6000]
    return llm.chat_json(RESUME_SYSTEM_PROMPT, RESUME_USER_TEMPLATE.format(resume_text=truncated))


def parse_resume(
    conn,
    raw_text: str,
    term_index: dict[str, int] | None = None,
    records: list[dict] | None = None,
    file_name: str | None = None,
) -> dict:
    """解析一份简历并落库（幂等：新建 resume_id）。

    返回 {resume_id, name, title, skills_json, dictionary_skills, llm_used}
    """
    raw_text = (raw_text or "").strip()
    if not raw_text:
        raise ValueError("简历内容为空")

    if records is None:
        records = compile_skills(conn)
    if term_index is None:
        term_index = build_term_index(conn)

    # ① 词典正则提取（主线：确定性、可溯源）
    dict_hits = extract_one(raw_text, records)

    # ② LLM 结构化提取（增强；失败自动降级为纯词典）
    structured = extract_structured(raw_text)
    llm_used = structured is not None
    name = title = ""
    if structured:
        name = str(structured.get("name") or "")
        title = str(structured.get("title") or "")
        # LLM 技能词映射本体后与词典命中合并（幻觉防控：匹配不上本体的词不入正式表）
        hit_ids = {h["skill_id"] for h in dict_hits}
        for term in structured.get("skills") or []:
            skill_id = _map_term_to_skill(str(term), term_index)
            if skill_id is not None and skill_id not in hit_ids:
                dict_hits.append({"skill_id": skill_id, "evidence": None, "l4_type": "llm"})
                hit_ids.add(skill_id)

    # 姓名兜底：raw_text 首行（源库人才简历多为"姓名\n头衔\n..."格式）
    if not name:
        first_line = raw_text.split("\n", 1)[0].strip()
        if first_line and len(first_line) <= 12:
            name = first_line

    resume_id = uuid.uuid4().hex[:12]
    conn.execute(
        """
        INSERT INTO resumes (resume_id, file_name, name, title, skills_json, raw_text)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            resume_id,
            file_name,
            name,
            title,
            json.dumps(structured, ensure_ascii=False) if structured else None,
            raw_text,
        ),
    )
    for h in dict_hits:
        source = "llm" if h["l4_type"] == "llm" else "dictionary"
        confidence = 0.85 if source == "llm" else 0.95
        conn.execute(
            """
            INSERT OR REPLACE INTO resume_skills (resume_id, skill_id, confidence, source)
            VALUES (?, ?, ?, ?)
            """,
            (resume_id, h["skill_id"], confidence, source),
        )
    conn.commit()
    return {
        "resume_id": resume_id,
        "name": name,
        "title": title,
        "skills_json": structured,
        "skill_ids": [h["skill_id"] for h in dict_hits],
        "llm_used": llm_used,
    }


def parse_file(conn, path: str | Path) -> dict:
    """从文件解析简历：.pdf 走 pypdf，其他按纯文本读取。"""
    p = Path(path)
    data = p.read_bytes()
    if p.suffix.lower() == ".pdf":
        raw_text = pdf_to_text(data)
        if not raw_text:
            raise ValueError(f"PDF 未提取到文本（可能为扫描件）: {p.name}")
    else:
        raw_text = data.decode("utf-8", errors="ignore")
    return parse_resume(conn, raw_text, file_name=p.name)


def main() -> None:
    parser = argparse.ArgumentParser(description="简历解析：PDF/文本 → 结构化字段 + 技能提取落库")
    parser.add_argument("--file", default=None, help="简历文件路径（.pdf/.txt）")
    parser.add_argument("--text", default=None, help="直接传入简历文本")
    args = parser.parse_args()

    conn = db.connect()
    db.init_db(conn)
    if args.file:
        result = parse_file(conn, args.file)
    elif args.text:
        result = parse_resume(conn, args.text)
    else:
        parser.error("需要 --file 或 --text 之一")
        return

    terms = conn.execute(
        """
        SELECT s.skill_term FROM resume_skills rs JOIN skills s ON rs.skill_id = s.skill_id
        WHERE rs.resume_id = ?
        """,
        (result["resume_id"],),
    ).fetchall()
    print(json.dumps({
        "resume_id": result["resume_id"],
        "name": result["name"],
        "title": result["title"],
        "llm_used": result["llm_used"],
        "skills": [r["skill_term"] for r in terms],
    }, ensure_ascii=False, indent=2))
    conn.close()


if __name__ == "__main__":
    main()
