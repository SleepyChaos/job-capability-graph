"""JD 导入：Excel/CSV 岗位文件 → 统一 jobs 表（幂等去重，可重复执行）。

列名兼容（别名自动识别）：
  岗位/title、公司/company、城市/city、薪资/salary、经验/experience、
  学历/education、JD描述/jd/description、来源平台/platform、收录时间/collect_time、链接/link
"""
from __future__ import annotations

import argparse
import re
import sqlite3

import pandas as pd

from . import db

COLUMN_ALIASES = {
    "title": ["岗位", "职位", "title", "岗位名称"],
    "company": ["公司", "company", "公司名称"],
    "city": ["城市", "city", "工作城市", "工作地"],
    "region": ["地区", "region"],
    "salary_text": ["薪资", "salary", "薪水", "薪资范围"],
    "experience": ["经验", "experience", "工作经验", "经验要求"],
    "education": ["学历", "education", "学历要求"],
    "headcount": ["招聘人数", "headcount"],
    "jd_text": ["jd描述", "岗位描述", "职位描述", "jd", "描述", "description"],
    "platform": ["来源平台", "platform", "来源"],
    "collect_time": ["收录时间", "collect_time", "发布时间"],
    "link": ["链接", "link", "url"],
    "source_file": ["source_file"],
}


def _find_column(df: pd.DataFrame, field: str) -> str | None:
    for alias in COLUMN_ALIASES[field]:
        for col in df.columns:
            if str(col).lower().replace(" ", "") == alias.lower().replace(" ", ""):
                return col
    return None


def parse_salary(salary_text) -> tuple[int | None, int | None]:
    """从 '20-30k' / '15-20K·13薪' 解析月薪范围（元）。移植自项目二 build_db.py。"""
    if pd.isna(salary_text):
        return None, None
    text = str(salary_text).strip().lower().replace("&amp;", "&")
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-~]\s*(\d+(?:\.\d+)?)\s*[k千]", text)
    if m:
        return int(float(m.group(1)) * 1000), int(float(m.group(2)) * 1000)
    m = re.search(r"(\d+(?:\.\d+)?)\s*[k千]", text)
    if m:
        v = int(float(m.group(1)) * 1000)
        return v, v
    return None, None


def _norm(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def import_file(conn: sqlite3.Connection, file_path: str) -> tuple[int, int]:
    """导入单个岗位文件，返回 (导入数, 去重跳过数)。"""
    if file_path.lower().endswith(".csv"):
        df = pd.read_csv(file_path)
    else:
        df = pd.read_excel(file_path)

    colmap = {field: _find_column(df, field) for field in COLUMN_ALIASES}
    if colmap["title"] is None:
        raise ValueError(f"{file_path}: 未找到岗位标题列")
    if colmap["jd_text"] is None:
        raise ValueError(f"{file_path}: 未找到 JD 描述列")

    source_name = file_path.rsplit("/", 1)[-1]
    inserted, skipped = 0, 0
    cur = conn.cursor()
    for idx, row in df.iterrows():
        title = _norm(row.get(colmap["title"]))
        company = _norm(row.get(colmap["company"])) if colmap["company"] else ""
        collect_time = _norm(row.get(colmap["collect_time"])) if colmap["collect_time"] else ""
        jd_text = _norm(row.get(colmap["jd_text"]))
        if not title or not jd_text:
            skipped += 1
            continue

        dedup_key = db.make_dedup_key(title, company, collect_time)
        exists = cur.execute("SELECT 1 FROM jobs WHERE dedup_key = ?", (dedup_key,)).fetchone()
        if exists:
            skipped += 1
            continue

        salary_text = _norm(row.get(colmap["salary_text"])) if colmap["salary_text"] else ""
        salary_min, salary_max = parse_salary(salary_text)
        job_id = f"{source_name}__{idx}"
        # job_id 冲突（同名文件二次导入但 collect_time 不同）时加后缀
        if cur.execute("SELECT 1 FROM jobs WHERE job_id = ?", (job_id,)).fetchone():
            job_id = f"{job_id}__{dedup_key[-6:]}"

        cur.execute(
            """
            INSERT INTO jobs (job_id, title, company, city, region, salary_text, salary_min,
                              salary_max, experience, education, headcount, jd_text, source_file,
                              platform, collect_time, link, dedup_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                title,
                company,
                _norm(row.get(colmap["city"])) if colmap["city"] else "",
                _norm(row.get(colmap["region"])) if colmap["region"] else "",
                salary_text,
                salary_min,
                salary_max,
                _norm(row.get(colmap["experience"])) if colmap["experience"] else "",
                _norm(row.get(colmap["education"])) if colmap["education"] else "",
                _norm(row.get(colmap["headcount"])) if colmap["headcount"] else "",
                jd_text,
                source_name,
                _norm(row.get(colmap["platform"])) if colmap["platform"] else "",
                collect_time,
                _norm(row.get(colmap["link"])) if colmap["link"] else "",
                dedup_key,
            ),
        )
        inserted += 1
    conn.commit()
    return inserted, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="导入 JD 文件到统一 jobs 表")
    parser.add_argument("files", nargs="+", help="岗位 Excel/CSV 文件")
    args = parser.parse_args()

    conn = db.connect()
    db.init_db(conn)
    total_in, total_skip = 0, 0
    for fp in args.files:
        inserted, skipped = import_file(conn, fp)
        total_in += inserted
        total_skip += skipped
        print(f"{fp}: 导入 {inserted} 条，去重跳过 {skipped} 条")
    count = conn.execute("SELECT COUNT(*) AS c FROM jobs").fetchone()["c"]
    print(f"导入完成：新增 {total_in} 条，jobs 总量 {count}")
    conn.close()


if __name__ == "__main__":
    main()
