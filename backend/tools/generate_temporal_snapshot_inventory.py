from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path


def quarter_start(value: str) -> str:
    dt = datetime.fromisoformat(value[:10])
    quarter = (dt.month - 1) // 3 + 1
    return f"{dt.year}-Q{quarter}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Inventory reproducible real-time JD snapshots.")
    parser.add_argument("--db", type=Path, default=Path(".local/dev.db"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    connection = sqlite3.connect(f"file:{args.db.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    total = cursor.execute("select count(*) from biz_job_posting").fetchone()[0]
    quality = {row[0]: row[1] for row in cursor.execute(
        "select time_quality_code, count(*) from biz_job_posting group by time_quality_code"
    )}
    rows = cursor.execute(
        """
        select job_posting_id, organization_id, published_at, source_collected_at
        from biz_job_posting
        where published_at is not null or source_collected_at is not null
        """
    ).fetchall()
    snapshots: dict[str, dict] = {}
    for row in rows:
        source_field = "published_at" if row["published_at"] else "source_collected_at"
        timestamp = row[source_field]
        key = quarter_start(timestamp)
        entry = snapshots.setdefault(key, {
            "snapshot": key, "job_ids": set(), "organization_ids": set(),
            "published_at_count": 0, "source_collected_at_fallback_count": 0,
        })
        entry["job_ids"].add(row["job_posting_id"])
        if row["organization_id"] is not None:
            entry["organization_ids"].add(row["organization_id"])
        count_key = "published_at_count" if source_field == "published_at" else "source_collected_at_fallback_count"
        entry[count_key] += 1

    result_rows = []
    for key in sorted(snapshots):
        item = snapshots[key]
        job_ids = list(item.pop("job_ids"))
        org_ids = item.pop("organization_ids")
        placeholders = ",".join("?" for _ in job_ids)
        tech_count = cursor.execute(
            f"select count(distinct technology_node_id) from biz_job_requirement where technology_node_id is not null and job_posting_id in ({placeholders})",
            job_ids,
        ).fetchone()[0]
        edge_count = cursor.execute(
            f"select count(*) from biz_job_requirement where technology_node_id is not null and job_posting_id in ({placeholders})",
            job_ids,
        ).fetchone()[0]
        result_rows.append({
            **item, "job_count": len(job_ids), "organization_count": len(org_ids),
            "technology_count": tech_count, "job_technology_edge_count": edge_count,
            "sample_sufficiency": "rough_ok" if len(job_ids) >= 30 else "insufficient_evidence",
        })
    result = {
        "status": "rough_inventory_not_formal_dynamic_evolution_acceptance",
        "database": str(args.db), "total_job_count": total,
        "time_quality_distribution": quality,
        "time_rule": "published_at first; source_collected_at only when published_at is absent; never use run date",
        "snapshot_count": len(result_rows), "snapshots": result_rows,
        "limitations": [
            "当前仅形成截面规模与关系数量盘点，尚未计算技能新增/消失和热度显著性",
            "需对source_collected_at回退样本单独披露，不能等同于真实发布日期",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
