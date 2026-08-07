"""词典导入：CSV 词典 → 统一技能本体（domains / l2_categories / l3_categories / skills）。

CSV 列：skill_term, skill_term_raw, l4_type, l1_code, l2_name, l3_name
幂等：重复执行不产生重复记录。
"""
from __future__ import annotations

import argparse
import csv

from . import config, db


def import_dictionary(conn, files: list) -> int:
    total = 0
    for fp in files:
        fp = str(fp)
        with open(fp, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                term = (row.get("skill_term") or "").strip()
                if not term:
                    continue
                l1_code = (row.get("l1_code") or "").strip()
                l1_name = config.L1_DOMAIN_NAMES.get(l1_code, l1_code)
                l2_name = (row.get("l2_name") or "").strip()
                l3_name = (row.get("l3_name") or "").strip()
                l4_type = (row.get("l4_type") or "细分词").strip()

                db.ensure_domain(conn, l1_code, l1_name)
                l2_id = None
                l3_id = None
                if l2_name:
                    l2_id = db.ensure_l2(conn, l1_code, l2_name)
                if l3_name and l2_id:
                    l3_id = db.ensure_l3(conn, l2_id, l3_name)
                db.ensure_skill(
                    conn,
                    term=term,
                    term_raw=(row.get("skill_term_raw") or term).strip(),
                    l4_type=l4_type,
                    l2_id=l2_id,
                    l3_id=l3_id,
                    l1_code=l1_code,
                )
                total += 1
    conn.commit()
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="导入技术词词典到统一技能本体")
    parser.add_argument(
        "--files", nargs="*", default=None, help="词典 CSV 文件（默认使用 config.DICTIONARY_FILES）"
    )
    args = parser.parse_args()
    files = args.files or config.DICTIONARY_FILES

    conn = db.connect()
    db.init_db(conn)
    n = import_dictionary(conn, files)
    stats = conn.execute(
        "SELECT (SELECT COUNT(*) FROM domains) AS d, (SELECT COUNT(*) FROM l2_categories) AS l2,"
        " (SELECT COUNT(*) FROM l3_categories) AS l3, (SELECT COUNT(*) FROM skills) AS s"
    ).fetchone()
    print(f"词典导入完成：处理 {n} 条记录")
    print(f"本体规模：L1={stats['d']} L2={stats['l2']} L3={stats['l3']} L4技能词={stats['s']}")
    conn.close()


if __name__ == "__main__":
    main()
