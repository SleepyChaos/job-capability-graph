"""聚类分类映射：聚类 → L1→L2→L3 技术分类体系（移植自项目二 classify_clusters.py）。

改造点：输入输出全部改为统一库（job_cluster_map + job_skills + skills 层级 JOIN），
不再依赖中间 JSON/Excel 文件。
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone

from . import db


def load_job_categories(conn: sqlite3.Connection) -> dict[str, dict]:
    rows = conn.execute(
        """
        SELECT js.job_id, s.l1_code, c2.l2_name, c3.l3_name
        FROM job_skills js
        JOIN skills s ON js.skill_id = s.skill_id
        LEFT JOIN l2_categories c2 ON s.l2_id = c2.l2_id
        LEFT JOIN l3_categories c3 ON s.l3_id = c3.l3_id
        WHERE js.review_status != 'rejected'
        """
    ).fetchall()
    result: dict[str, dict] = defaultdict(
        lambda: {"l1_codes": Counter(), "l2_names": Counter(), "l3_names": Counter()}
    )
    for r in rows:
        entry = result[r["job_id"]]
        if r["l1_code"]:
            entry["l1_codes"][r["l1_code"]] += 1
        if r["l2_name"]:
            entry["l2_names"][r["l2_name"]] += 1
        if r["l3_name"]:
            entry["l3_names"][r["l3_name"]] += 1
    return dict(result)


def classify_cluster(cluster_row, member_ids: list[str], job_cats: dict) -> dict:
    total = len(member_ids)
    agg_l1, agg_l2, agg_l3 = Counter(), Counter(), Counter()
    jobs_with_cat = 0
    for jid in member_ids:
        cats = job_cats.get(jid)
        if not cats:
            continue
        agg_l1.update(cats["l1_codes"])
        agg_l2.update(cats["l2_names"])
        agg_l3.update(cats["l3_names"])
        if cats["l2_names"]:
            jobs_with_cat += 1

    return {
        "cluster_id": cluster_row["cluster_id"],
        "job_count": total,
        "primary_l1_code": agg_l1.most_common(1)[0][0] if agg_l1 else "",
        "primary_l2_name": agg_l2.most_common(1)[0][0] if agg_l2 else "",
        "primary_l2_coverage": round(agg_l2.most_common(1)[0][1] / total, 4)
        if (agg_l2 and total)
        else 0,
        "primary_l3_name": agg_l3.most_common(1)[0][0] if agg_l3 else "",
        "category_ratio": round(jobs_with_cat / total, 4) if total else 0,
        "l1_distribution": dict(agg_l1.most_common(10)),
        "l2_distribution": dict(agg_l2.most_common(10)),
        "l3_distribution": dict(agg_l3.most_common(10)),
    }


def run_classification(conn: sqlite3.Connection) -> int:
    job_cats = load_job_categories(conn)
    clusters = conn.execute("SELECT cluster_id, clustered_at FROM clusters").fetchall()
    members: dict[str, list[str]] = defaultdict(list)
    for r in conn.execute("SELECT cluster_id, job_id FROM job_cluster_map").fetchall():
        members[r["cluster_id"]].append(r["job_id"])

    now = datetime.now(timezone.utc).isoformat()
    cur = conn.cursor()
    cur.execute("DELETE FROM cluster_classifications")
    for c in clusters:
        result = classify_cluster(c, members.get(c["cluster_id"], []), job_cats)
        cur.execute(
            """
            INSERT INTO cluster_classifications
            (cluster_id, job_count, primary_l1_code, primary_l2_name, primary_l2_coverage,
             primary_l3_name, category_ratio, l1_distribution, l2_distribution, l3_distribution,
             classified_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result["cluster_id"], result["job_count"], result["primary_l1_code"],
                result["primary_l2_name"], result["primary_l2_coverage"],
                result["primary_l3_name"], result["category_ratio"],
                json.dumps(result["l1_distribution"], ensure_ascii=False),
                json.dumps(result["l2_distribution"], ensure_ascii=False),
                json.dumps(result["l3_distribution"], ensure_ascii=False),
                now,
            ),
        )
    conn.commit()
    db.set_meta(conn, "last_classified_at", now)
    conn.commit()

    # 汇总打印
    l1_counter = Counter()
    for r in cur.execute("SELECT primary_l1_code FROM cluster_classifications").fetchall():
        if r["primary_l1_code"]:
            l1_counter[r["primary_l1_code"]] += 1
    print("L1 分类分布（按聚类数）:")
    for l1, cnt in sorted(l1_counter.items()):
        print(f"  {l1}: {cnt} 个聚类")
    return len(clusters)


def main() -> None:
    parser = argparse.ArgumentParser(description="聚类映射回 L1→L2→L3 分类体系")
    parser.parse_args()
    conn = db.connect()
    db.init_db(conn)
    n = run_classification(conn)
    print(f"分类完成：{n} 个聚类")
    conn.close()


if __name__ == "__main__":
    main()
