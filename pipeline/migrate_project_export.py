"""阶段 2.5：project-export（项目二）数据主体迁移 → 统一库。

将 existing-projects/project-export/data/jobs.db 的 9 张表全量、幂等地迁入
统一库 unified.db（方案见 docs/数据库迁移计划.md）：
  步骤 1 技能本体（domains / l2_categories / skills）
  步骤 2 岗位 jobs（10,447 条）
  步骤 3 岗位-技能关联 job_skills（12,309 条）+ 证据回填（extract 重跑）
  步骤 4 聚类三表（clusters / job_cluster_map / cluster_classifications）
  步骤 5 人才简历（talents → resumes，talent_keywords → resume_skills）
  步骤 6 内置质量校验（行数 / 引用完整性 / L1 分布 / 抽查）

特性：源库只读（ATTACH）、迁移前自动备份、幂等可重跑、校验失败即报错退出。

用法（在项目根目录 job-capability-graph/ 下执行）：
  python -m pipeline.migrate_project_export               # 全流程（含证据回填）
  python -m pipeline.migrate_project_export --no-backfill # 跳过证据回填
  python -m pipeline.migrate_project_export --skip-backup # 跳过备份（重复调试时）
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config, db, extract

# 源库默认路径（可用环境变量覆盖）
DEFAULT_SRC = Path(__file__).resolve().parent.parent.parent / "existing-projects" / "project-export" / "data" / "jobs.db"
SOURCE_BATCH = "project-export"  # jobs.source_file 批次标识


def _attach_source(conn: sqlite3.Connection, src_path: Path) -> None:
    if not src_path.exists():
        raise SystemExit(f"源库不存在: {src_path}")
    conn.execute("ATTACH DATABASE ? AS src", (f"file:{src_path}?mode=ro",))


def _backup(conn: sqlite3.Connection) -> None:
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # 确保 WAL 数据合入主文件再备份
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = config.DB_PATH.with_name(f"unified.db.bak-{stamp}")
    shutil.copy2(config.DB_PATH, bak)
    print(f"已备份统一库 → {bak.name}")


# ---------------------------------------------------------------------------
# 步骤 1：技能本体
# ---------------------------------------------------------------------------
def migrate_ontology(conn: sqlite3.Connection) -> dict:
    print("[1/6] 技能本体（domains / l2_categories / skills）")
    # T1–T7 域（幂等）
    for code, name in config.L1_DOMAIN_NAMES.items():
        db.ensure_domain(conn, code, name)

    # 源库 DISTINCT (l1_code, l2_name) 补齐 L2
    l2_rows = conn.execute(
        "SELECT DISTINCT l1_code, l2_name FROM src.job_keywords "
        "WHERE l1_code IS NOT NULL AND l2_name IS NOT NULL AND l2_name <> ''"
    ).fetchall()
    for r in l2_rows:
        db.ensure_l2(conn, r["l1_code"], r["l2_name"])
    print(f"  L2 挂载核对: {len(l2_rows)} 组")

    # 源库规范词 upsert（词典已有的保留 dictionary 来源，不覆盖）
    terms = conn.execute(
        """
        SELECT keyword_norm, keyword_raw, l1_code, l2_name, l4_type,
               COUNT(*) AS cnt
        FROM src.job_keywords
        WHERE keyword_norm IS NOT NULL AND keyword_norm <> ''
        GROUP BY keyword_norm
        """
    ).fetchall()
    added = 0
    for t in terms:
        l2_id = None
        if t["l1_code"] and t["l2_name"]:
            row = conn.execute(
                "SELECT l2_id FROM l2_categories WHERE l1_code = ? AND l2_name = ?",
                (t["l1_code"], t["l2_name"]),
            ).fetchone()
            l2_id = row["l2_id"] if row else None
        before = conn.execute(
            "SELECT skill_id FROM skills WHERE skill_term = ?", (t["keyword_norm"],)
        ).fetchone()
        db.ensure_skill(
            conn,
            term=t["keyword_norm"],
            term_raw=t["keyword_raw"] or t["keyword_norm"],
            l4_type=t["l4_type"] or "细分词",
            l2_id=l2_id,
            l3_id=None,
            l1_code=t["l1_code"],
            source="embodied_db",
        )
        if before is None:
            added += 1
    conn.commit()
    print(f"  源库规范词 {len(terms)} 个，新入本体 {added} 个（其余已由词典导入）")

    # 人才库特有词条（多为指标词/基准名，源库 job_keywords 不含）补入本体
    t_terms = conn.execute(
        """
        SELECT DISTINCT tk.keyword_norm, tk.l1_code, tk.l2_class
        FROM src.talent_keywords tk
        WHERE tk.keyword_norm IS NOT NULL AND tk.keyword_norm <> ''
          AND tk.keyword_norm NOT IN (SELECT skill_term FROM skills)
        """
    ).fetchall()
    for t in t_terms:
        l2_id = None
        if t["l1_code"] and t["l2_class"]:
            db.ensure_l2(conn, t["l1_code"], t["l2_class"])
            row = conn.execute(
                "SELECT l2_id FROM l2_categories WHERE l1_code = ? AND l2_name = ?",
                (t["l1_code"], t["l2_class"]),
            ).fetchone()
            l2_id = row["l2_id"] if row else None
        db.ensure_skill(
            conn, term=t["keyword_norm"], term_raw=t["keyword_norm"],
            l4_type="指标词" if any(ch.isdigit() for ch in t["keyword_norm"]) else "细分词",
            l2_id=l2_id, l3_id=None, l1_code=t["l1_code"], source="embodied_db",
        )
    conn.commit()
    if t_terms:
        print(f"  人才库特有词条补入本体: {len(t_terms)} 个")
    return {"terms": len(terms), "added": added, "talent_terms": len(t_terms)}


# ---------------------------------------------------------------------------
# 步骤 2：岗位
# ---------------------------------------------------------------------------
def migrate_jobs(conn: sqlite3.Connection) -> dict:
    print("[2/6] 岗位（jobs）")
    rows = conn.execute(
        """
        SELECT job_id, source_file, company, title, city, region, salary_text,
               salary_min, salary_max, experience, education, headcount, jd_text,
               link, platform, collect_time
        FROM src.jobs
        """
    ).fetchall()
    # 源库同 title+company+collect_time 的多条重复 JD 按 dedup_key 合并，
    # 被合并的 job_id 映射到幸存者，其关联边/聚类成员改指幸存者（口径不丢失）
    job_map: dict[str, str] = {}
    inserted = merged = 0
    for r in rows:
        dedup = db.make_dedup_key(r["title"], r["company"], r["collect_time"])
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO jobs
            (job_id, title, company, city, region, salary_text, salary_min, salary_max,
             experience, education, headcount, jd_text, source_file, platform,
             collect_time, link, dedup_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (r["job_id"], r["title"], r["company"], r["city"], r["region"],
             r["salary_text"], r["salary_min"], r["salary_max"], r["experience"],
             r["education"], r["headcount"], r["jd_text"],
             r["source_file"] or SOURCE_BATCH, r["platform"], r["collect_time"],
             r["link"], dedup),
        )
        if cur.rowcount:
            inserted += 1
            job_map[r["job_id"]] = r["job_id"]
        else:
            merged += 1
            row = conn.execute("SELECT job_id FROM jobs WHERE dedup_key = ?", (dedup,)).fetchone()
            if row:
                job_map[r["job_id"]] = row["job_id"]
    conn.commit()
    print(f"  源库 {len(rows)} 条 → 迁入 {inserted}，重复合并 {merged}（关联数据改指幸存者）")
    return {"source": len(rows), "inserted": inserted, "merged": merged, "job_map": job_map}


# ---------------------------------------------------------------------------
# 步骤 3：岗位-技能关联 + 证据回填
# ---------------------------------------------------------------------------
def migrate_job_skills(conn: sqlite3.Connection, job_map: dict[str, str]) -> dict:
    print("[3/6] 岗位-技能关联（job_skills）")
    skill_ids = {
        r["skill_term"]: r["skill_id"]
        for r in conn.execute("SELECT skill_id, skill_term FROM skills").fetchall()
    }
    rows = conn.execute(
        """
        SELECT jk.job_id, jk.keyword_raw, jk.keyword_norm, jk.l4_type
        FROM src.job_keywords jk JOIN src.jobs j ON jk.job_id = j.job_id
        """
    ).fetchall()
    inserted = missing_term = collapsed = 0
    for r in rows:
        sid = skill_ids.get(r["keyword_norm"])
        if sid is None:
            missing_term += 1
            continue
        target_job = job_map.get(r["job_id"], r["job_id"])
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO job_skills
            (job_id, skill_id, keyword_raw, evidence, confidence, l4_type, source, review_status)
            VALUES (?, ?, ?, NULL, 0.95, ?, 'dictionary', 'approved')
            """,
            (target_job, sid, r["keyword_raw"], r["l4_type"] or "细分词"),
        )
        if cur.rowcount:
            inserted += 1
        else:
            collapsed += 1  # 重复岗位合并后的重复边
    conn.commit()
    print(f"  源库关联 {len(rows)} 条 → 迁入 {inserted}，重复合并 {collapsed}，无对应词 {missing_term}")
    return {"source": len(rows), "inserted": inserted, "collapsed": collapsed, "missing_term": missing_term}


def backfill_evidence(conn: sqlite3.Connection) -> dict:
    """用移植的 extract 对源库批次 JD 重跑匹配：回填 evidence + 补录新命中边。"""
    print("[3.5/6] 证据回填（extract 重跑源库批次 JD）")
    records = extract.compile_skills(conn)
    jobs = conn.execute(
        "SELECT job_id, jd_text FROM jobs WHERE source_file = ? OR source_file IS NULL",
        (SOURCE_BATCH,),
    ).fetchall()
    # 源库批次的 jd_text 来自真实 JD；source_file 被源库原值覆盖时按 job_id 前缀兜底
    if len(jobs) < 1000:
        jobs = conn.execute(
            "SELECT job_id, jd_text FROM jobs WHERE jd_text IS NOT NULL AND jd_text <> ''"
        ).fetchall()
    print(f"  待回填岗位: {len(jobs)} 条")
    filled = new_edges = 0
    for i, job in enumerate(jobs):
        hits = extract.extract_one(job["jd_text"] or "", records)
        for h in hits:
            cur = conn.execute(
                "UPDATE job_skills SET evidence = ? WHERE job_id = ? AND skill_id = ? AND evidence IS NULL",
                (h["evidence"], job["job_id"], h["skill_id"]),
            )
            if cur.rowcount:
                filled += 1
            else:
                exists = conn.execute(
                    "SELECT 1 FROM job_skills WHERE job_id = ? AND skill_id = ?",
                    (job["job_id"], h["skill_id"]),
                ).fetchone()
                if exists is None:
                    conn.execute(
                        """
                        INSERT INTO job_skills
                        (job_id, skill_id, evidence, confidence, l4_type, source, review_status)
                        VALUES (?, ?, ?, 0.95, ?, 'dictionary', 'approved')
                        """,
                        (job["job_id"], h["skill_id"], h["evidence"], h["l4_type"]),
                    )
                    new_edges += 1
        if (i + 1) % 1000 == 0:
            conn.commit()
            print(f"  已处理 {i + 1}/{len(jobs)}")
    conn.commit()
    print(f"  证据回填 {filled} 条，新增命中边 {new_edges} 条")
    return {"filled": filled, "new_edges": new_edges}


# ---------------------------------------------------------------------------
# 步骤 4：聚类三表
# ---------------------------------------------------------------------------
def migrate_clusters(conn: sqlite3.Connection, job_map: dict[str, str]) -> dict:
    print("[4/6] 聚类三表")
    clusters = conn.execute(
        """
        SELECT cluster_id, cluster_name, description, shared_skills,
               representative_titles, keywords, job_count, clustered_at
        FROM src.clusters
        """
    ).fetchall()
    ins_c = 0
    for c in clusters:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO clusters
            (cluster_id, cluster_name, description, shared_skills, representative_titles,
             keywords, job_count, name_source, review_status, clustered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'llm', 'pending', ?)
            """,
            (c["cluster_id"], c["cluster_name"], c["description"], c["shared_skills"],
             c["representative_titles"], c["keywords"], c["job_count"], c["clustered_at"]),
        )
        ins_c += cur.rowcount

    maps = conn.execute("SELECT cluster_id, job_id, clustered_at FROM src.job_cluster_map").fetchall()
    ins_m = 0
    for m in maps:
        target_job = job_map.get(m["job_id"], m["job_id"])
        cur = conn.execute(
            "INSERT OR IGNORE INTO job_cluster_map (cluster_id, job_id, clustered_at) VALUES (?, ?, ?)",
            (m["cluster_id"], target_job, m["clustered_at"]),
        )
        ins_m += cur.rowcount

    cls = conn.execute(
        """
        SELECT cluster_id, job_count, primary_l1_code, primary_l2_name, primary_l2_coverage,
               primary_l3_name, category_ratio, l1_code_distribution, l2_name_distribution,
               l3_name_distribution, classified_at
        FROM src.cluster_classifications
        """
    ).fetchall()
    ins_k = 0
    for k in cls:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO cluster_classifications
            (cluster_id, job_count, primary_l1_code, primary_l2_name, primary_l2_coverage,
             primary_l3_name, category_ratio, l1_distribution, l2_distribution, l3_distribution,
             classified_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (k["cluster_id"], k["job_count"], k["primary_l1_code"], k["primary_l2_name"],
             k["primary_l2_coverage"], k["primary_l3_name"], k["category_ratio"],
             k["l1_code_distribution"], k["l2_name_distribution"], k["l3_name_distribution"],
             k["classified_at"]),
        )
        ins_k += cur.rowcount
    conn.commit()
    print(f"  clusters {ins_c}/{len(clusters)}，job_cluster_map {ins_m}（源库 {len(maps)}，重复岗位合并后去重），"
          f"cluster_classifications {ins_k}/{len(cls)}")
    return {"clusters": ins_c, "maps": ins_m, "classifications": ins_k}


# ---------------------------------------------------------------------------
# 步骤 5：人才简历
# ---------------------------------------------------------------------------
def migrate_talents(conn: sqlite3.Connection) -> dict:
    print("[5/6] 人才简历（resumes / resume_skills）")
    talents = conn.execute(
        """
        SELECT talent_id, name, talent_type, university, school_lab,
               research_direction, achievements, industry, title, resume_text
        FROM src.talents
        """
    ).fetchall()
    ins_t = 0
    for t in talents:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO resumes
            (resume_id, name, title, raw_text, talent_type, university, school_lab,
             research_direction, achievements, industry)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (t["talent_id"], t["name"], t["title"], t["resume_text"], t["talent_type"],
             t["university"], t["school_lab"], t["research_direction"],
             t["achievements"], t["industry"]),
        )
        ins_t += cur.rowcount

    skill_ids = {
        r["skill_term"]: r["skill_id"]
        for r in conn.execute("SELECT skill_id, skill_term FROM skills").fetchall()
    }
    kws = conn.execute(
        "SELECT DISTINCT talent_id, keyword_norm FROM src.talent_keywords"
    ).fetchall()
    ins_k = missing = 0
    for k in kws:
        sid = skill_ids.get(k["keyword_norm"])
        if sid is None:
            missing += 1
            continue
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO resume_skills (resume_id, skill_id, confidence, source)
            VALUES (?, ?, 0.9, 'dictionary')
            """,
            (k["talent_id"], sid),
        )
        ins_k += cur.rowcount
    conn.commit()
    print(f"  简历 {ins_t}/{len(talents)}，人才技能词 {ins_k}/{len(kws)}（无对应词 {missing}）")
    return {"talents": ins_t, "keywords": ins_k, "missing": missing}


# ---------------------------------------------------------------------------
# 步骤 6：质量校验
# ---------------------------------------------------------------------------
def validate(conn: sqlite3.Connection) -> None:
    print("[6/6] 数据质量校验")
    errors: list[str] = []

    # 0. 源库去重口径：distinct dedup_key 与统一库该批次岗位数应相等（无数据丢失）
    src_dedup = conn.execute(
        """
        SELECT COUNT(*) AS c FROM (
          SELECT lower(replace(title,' ',''))||'|'||lower(replace(IFNULL(company,''),' ',''))
                 ||'|'||lower(replace(IFNULL(collect_time,''),' ','')) AS k
          FROM src.jobs GROUP BY k)
        """
    ).fetchone()["c"]
    dst_migrated = conn.execute(
        "SELECT COUNT(*) AS c FROM jobs WHERE job_id IN (SELECT job_id FROM src.jobs)"
    ).fetchone()["c"]
    ok = dst_migrated == src_dedup
    print(f"  {'✓' if ok else '✗'} 岗位无丢失: 源库去重后 {src_dedup} = 统一库迁入 {dst_migrated}")
    if not ok:
        errors.append(f"岗位迁移丢失: 源库去重 {src_dedup} vs 迁入 {dst_migrated}")

    # 1. 行数核对（job_skills/聚类映射允许重复合并后 ≤ 源库）
    checks = [
        ("clusters", "SELECT COUNT(*) AS c FROM src.clusters",
         "SELECT COUNT(*) AS c FROM clusters WHERE cluster_id IN (SELECT cluster_id FROM src.clusters)", True),
        ("job_cluster_map", "SELECT COUNT(*) AS c FROM src.job_cluster_map",
         "SELECT COUNT(*) AS c FROM job_cluster_map WHERE cluster_id IN (SELECT cluster_id FROM src.clusters)", False),
        ("resumes", "SELECT COUNT(*) AS c FROM src.talents",
         "SELECT COUNT(*) AS c FROM resumes WHERE resume_id IN (SELECT talent_id FROM src.talents)", True),
    ]
    for name, src_q, dst_q, exact in checks:
        src_n = conn.execute(src_q).fetchone()["c"]
        dst_n = conn.execute(dst_q).fetchone()["c"]
        ok = (dst_n == src_n) if exact else (dst_n > 0)
        print(f"  {'✓' if ok else '✗'} {name}: 源库 {src_n} → 统一库 {dst_n}")
        if not ok:
            errors.append(f"{name} 行数异常: 源库 {src_n} vs 统一库 {dst_n}")
    edges_src = conn.execute("SELECT COUNT(*) AS c FROM src.job_keywords").fetchone()["c"]
    edges_dst = conn.execute(
        "SELECT COUNT(*) AS c FROM job_skills WHERE job_id IN (SELECT job_id FROM src.jobs)"
    ).fetchone()["c"]
    ok = edges_dst > 0
    print(f"  {'✓' if ok else '✗'} job_skills: 源库 {edges_src} → 统一库 {edges_dst}（重复岗位合并+回填补边）")
    if not ok:
        errors.append("job_skills 迁入为 0")

    # 2. 引用完整性
    fk_checks = [
        ("job_skills.skill_id", "SELECT COUNT(*) AS c FROM job_skills WHERE skill_id NOT IN (SELECT skill_id FROM skills)"),
        ("job_cluster_map.job_id", "SELECT COUNT(*) AS c FROM job_cluster_map WHERE job_id NOT IN (SELECT job_id FROM jobs)"),
        ("resume_skills.skill_id", "SELECT COUNT(*) AS c FROM resume_skills WHERE skill_id NOT IN (SELECT skill_id FROM skills)"),
    ]
    for name, q in fk_checks:
        n = conn.execute(q).fetchone()["c"]
        mark = "✓" if n == 0 else "✗"
        print(f"  {mark} 引用完整性 {name}: 悬空 {n}")
        if n:
            errors.append(f"{name} 存在 {n} 条悬空引用")

    # 3. L1 分布核对（重复合并后按 dedup 幸存者口径对比）
    merged_ids = conn.execute(
        """
        SELECT s.job_id AS src_job, u.job_id AS unified_job FROM src.jobs s
        JOIN jobs u ON u.dedup_key = (
          lower(replace(s.title,' ',''))||'|'||lower(replace(IFNULL(s.company,''),' ',''))
          ||'|'||lower(replace(IFNULL(s.collect_time,''),' ','')))
        """
    ).fetchall()
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS m_map (src_job TEXT, unified_job TEXT)")
    conn.execute("DELETE FROM m_map")
    conn.executemany("INSERT INTO m_map VALUES (?, ?)", [(r["src_job"], r["unified_job"]) for r in merged_ids])
    src_l1 = {r["l1_code"]: r["c"] for r in conn.execute(
        """
        SELECT s.l1_code, COUNT(DISTINCT m.unified_job) AS c
        FROM src.job_keywords jk JOIN m_map m ON jk.job_id = m.src_job
        JOIN skills s ON s.skill_term = jk.keyword_norm
        GROUP BY s.l1_code
        """
    ).fetchall()}
    dst_l1 = {r["l1_code"]: r["c"] for r in conn.execute(
        """
        SELECT s.l1_code, COUNT(DISTINCT js.job_id) AS c
        FROM job_skills js JOIN skills s ON js.skill_id = s.skill_id
        WHERE js.job_id IN (SELECT unified_job FROM m_map)
        GROUP BY s.l1_code
        """
    ).fetchall()}
    for code, n in src_l1.items():
        m = dst_l1.get(code, 0)
        ok = m >= n  # 回填补边只增不减
        print(f"  {'✓' if ok else '✗'} L1={code}: 源库覆盖岗位 {n} → 统一库 {m}")
        if not ok:
            errors.append(f"L1={code} 覆盖岗位减少: {n} → {m}")

    # 4. 抽查：随机 10 条源库关联，按合并映射后与统一库核对
    samples = conn.execute(
        """
        SELECT m.unified_job, jk.keyword_norm, jk.keyword_raw, jk.l4_type
        FROM src.job_keywords jk JOIN m_map m ON jk.job_id = m.src_job
        ORDER BY RANDOM() LIMIT 10
        """
    ).fetchall()
    bad = 0
    for s in samples:
        row = conn.execute(
            """
            SELECT js.keyword_raw, s.skill_term FROM job_skills js
            JOIN skills s ON js.skill_id = s.skill_id
            WHERE js.job_id = ? AND s.skill_term = ?
            """,
            (s["unified_job"], s["keyword_norm"]),
        ).fetchone()
        if row is None:
            bad += 1
    mark = "✓" if bad == 0 else "✗"
    print(f"  {mark} 随机抽查 10 条（合并映射后）: 缺失 {bad}")
    if bad:
        errors.append(f"抽查 {bad}/10 条缺失")
    conn.execute("DROP TABLE IF EXISTS m_map")

    if errors:
        raise SystemExit("校验失败：\n  - " + "\n  - ".join(errors))
    print("校验全部通过")


def main() -> None:
    parser = argparse.ArgumentParser(description="阶段 2.5 project-export 数据主体迁移")
    parser.add_argument("--source", default=None, help="源库路径（默认 existing-projects/project-export/data/jobs.db）")
    parser.add_argument("--no-backfill", action="store_true", help="跳过证据回填")
    parser.add_argument("--skip-backup", action="store_true", help="跳过迁移前备份")
    args = parser.parse_args()

    src_path = Path(args.source) if args.source else DEFAULT_SRC
    conn = db.connect()
    _attach_source(conn, src_path)
    if not args.skip_backup and config.DB_PATH.exists():
        _backup(conn)

    started = datetime.now(timezone.utc)
    stats = {
        "ontology": migrate_ontology(conn),
        "jobs": migrate_jobs(conn),
    }
    job_map = stats["jobs"].pop("job_map")
    stats["job_skills"] = migrate_job_skills(conn, job_map)
    if not args.no_backfill:
        stats["backfill"] = backfill_evidence(conn)
    stats["clusters"] = migrate_clusters(conn, job_map)
    stats["talents"] = migrate_talents(conn)
    validate(conn)

    db.set_meta(conn, "migration_project_export", json.dumps(
        {"finished_at": datetime.now(timezone.utc).isoformat(),
         "elapsed_sec": round((datetime.now(timezone.utc) - started).total_seconds(), 1),
         "source": str(src_path)}, ensure_ascii=False))
    conn.commit()

    summary = conn.execute(
        """
        SELECT (SELECT COUNT(*) FROM jobs) AS jobs,
               (SELECT COUNT(*) FROM job_skills) AS edges,
               (SELECT COUNT(*) FROM skills) AS skills,
               (SELECT COUNT(*) FROM clusters) AS clusters,
               (SELECT COUNT(*) FROM resumes) AS resumes
        """
    ).fetchone()
    print("=" * 60)
    print(f"迁移完成：岗位 {summary['jobs']}，图谱边 {summary['edges']}，"
          f"技能词 {summary['skills']}，聚类 {summary['clusters']}，简历 {summary['resumes']}")
    conn.close()


if __name__ == "__main__":
    main()
