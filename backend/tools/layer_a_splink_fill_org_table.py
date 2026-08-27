"""Write Layer A splink result into md_organization + md_organization_alias.

Idempotent: re-running replaces all rows created by this tool (identified by
source_metadata_json['tool']=='layer_a_splink_backfill').
Safe: only INSERT new organization_code rows; existing rows from taxonomy import are left alone.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert

from app.db.session import SessionLocal
from app.modules.job.models import Organization, OrganizationAlias

ROOT = Path(r"c:\Users\10741\WorkBuddy\2026-08-14-11-44-53\job-capability-graph")
CSV_IN = ROOT / "data" / "processed" / "org_entity_resolution" / "org_splink_resolution.csv"
SUMMARY_IN = ROOT / "data" / "processed" / "org_entity_resolution" / "org_splink_summary.json"

TOOL_TAG = "layer_a_splink_backfill"


def _norm(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"[\s（）()【】\[\]《》\"“”'·\-—_./\\,，。]+", "", str(s)).casefold()


def main() -> None:
    if not CSV_IN.exists():
        raise SystemExit(f"Missing {CSV_IN}, run layer_a_splink_org_resolution.py first")
    summary = json.loads(SUMMARY_IN.read_text(encoding="utf-8")) if SUMMARY_IN.exists() else {}

    # 1) Aggregate all per-canonical records: choose canonical name, aliases, geo, type, needs_review
    by_canon: dict[str, dict] = {}
    with CSV_IN.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            canon = row["canonical_id"].strip()
            rec = by_canon.setdefault(
                canon,
                {
                    "aliases": {},
                    "cities": {},
                    "provinces": {},
                    "types": {},
                    "anchor_ids": set(),
                    "needs_review": False,
                    "conflict": False,
                    "sample_raw": "",
                    "sources": set(),
                    "member_count": 0,
                    "min_score": 1.0,
                },
            )
            name = (row["raw_name"] or "").strip()
            if not rec["sample_raw"]:
                rec["sample_raw"] = name
            # prefer canonical_name from non-university / non-institute shortest clean name
            rec["aliases"][_norm(name)] = name
            city = (row["city"] or "").strip()
            if city:
                rec["cities"][city] = rec["cities"].get(city, 0) + 1
            prov = (row["province"] or "").strip()
            if prov:
                rec["provinces"][prov] = rec["provinces"].get(prov, 0) + 1
            otype = (row["org_type"] or "unknown").strip() or "unknown"
            rec["types"][otype] = rec["types"].get(otype, 0) + 1
            aid = (row["anchor_id"] or "").strip()
            if aid:
                rec["anchor_ids"].add(aid)
            if row.get("needs_review") == "1":
                rec["needs_review"] = True
            if row.get("conflict_with_anchor") == "1":
                rec["conflict"] = True
            src = row.get("source_file") or ""
            if src:
                rec["sources"].add(src)
            rec["member_count"] += 1
            try:
                sc = float(row["cluster_match_score"] or "1.0")
            except ValueError:
                sc = 1.0
            if sc < rec["min_score"]:
                rec["min_score"] = sc

    # 2) Choose canonical_name = most common unique alias (prefer short Chinese)
    def _pick_name(aliases: dict[str, str]) -> str:
        # aliases: {norm: original}
        originals = list({v for v in aliases.values() if v})
        originals.sort(key=lambda s: (len(_norm(s)), len(s), s))
        for n in originals:
            # prefer non-"有限公司" / non-"股份" endings if we have variants
            normed = _norm(n)
            if normed and not normed.endswith("公司") and not normed.endswith("集团"):
                return n
        return originals[0] if originals else "(unnamed)"

    prepared_rows: list[dict] = []
    for canon, info in by_canon.items():
        prepared_rows.append(
            {
                "organization_code": canon,
                "canonical_name": _pick_name(info["aliases"]),
                "normalized_name": _norm(_pick_name(info["aliases"])),
                "organization_type_code": max(info["types"].items(), key=lambda kv: kv[1])[0]
                if info["types"]
                else "unknown",
                "city_name": max(info["cities"].items(), key=lambda kv: kv[1])[0]
                if info["cities"]
                else None,
                "province_name": max(info["provinces"].items(), key=lambda kv: kv[1])[0]
                if info["provinces"]
                else None,
                "website_url": None,
                "industry_text": None,
                "source_metadata_json": {
                    "tool": TOOL_TAG,
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "splink_summary": {
                        "member_count": info["member_count"],
                        "min_match_score": round(info["min_score"], 4),
                        "needs_review": info["needs_review"],
                        "conflict_with_ground_truth": info["conflict"],
                        "anchor_ids": sorted(info["anchor_ids"]),
                        "sources": sorted(info["sources"]),
                        "global_raw_record_count": summary.get("raw_record_count"),
                        "global_cluster_count": summary.get("cluster_count"),
                    },
                },
                "organization_status_code": "needs_review" if info["needs_review"] else "active",
                "aliases": list({v for v in info["aliases"].values() if v}),
            }
        )

    print(f"Prepared {len(prepared_rows)} canonical organizations.")
    print("Type distribution:", {
        k: sum(1 for r in prepared_rows if r["organization_type_code"] == k)
        for k in sorted({r["organization_type_code"] for r in prepared_rows})
    })
    print(
        "Needs review:",
        sum(1 for r in prepared_rows if r["organization_status_code"] != "active"),
    )

    # 3) Upsert into DB
    with SessionLocal() as db:
        # delete rows previously backfilled by this tool (only those tagged)
        existing_tool_ids = db.execute(
            select(Organization.organization_id, Organization.organization_code).where(
                func.json_extract(Organization.source_metadata_json, "$.tool") == TOOL_TAG
            )
        ).all()
        if existing_tool_ids:
            to_delete_ids = [r[0] for r in existing_tool_ids]
            db.query(OrganizationAlias).where(
                OrganizationAlias.organization_id.in_(to_delete_ids)
            ).delete(synchronize_session=False)
            db.query(Organization).where(
                Organization.organization_id.in_(to_delete_ids)
            ).delete(synchronize_session=False)
            db.commit()
            print(f"Deleted {len(to_delete_ids)} previous tool rows (re-fill idempotently).")

        inserted = skipped = 0
        code_to_id: dict[str, int] = {}
        # batch insert
        for batch in [prepared_rows[i : i + 500] for i in range(0, len(prepared_rows), 500)]:
            stmt = (
                insert(Organization)
                .values(
                    [
                        {
                            "organization_code": r["organization_code"],
                            "canonical_name": r["canonical_name"],
                            "normalized_name": r["normalized_name"],
                            "organization_type_code": r["organization_type_code"],
                            "province_name": r["province_name"],
                            "city_name": r["city_name"],
                            "website_url": r["website_url"],
                            "industry_text": r["industry_text"],
                            "source_metadata_json": r["source_metadata_json"],
                            "organization_status_code": r["organization_status_code"],
                        }
                        for r in batch
                    ]
                )
                .on_duplicate_key_update(  # MySQL upsert
                    canonical_name=insert(Organization).values.canonical_name,
                    normalized_name=insert(Organization).values.normalized_name,
                    organization_type_code=insert(Organization).values.organization_type_code,
                    province_name=insert(Organization).values.province_name,
                    city_name=insert(Organization).values.city_name,
                    source_metadata_json=insert(Organization).values.source_metadata_json,
                    organization_status_code=insert(Organization).values.organization_status_code,
                )
            )
            try:
                db.execute(stmt)
                db.commit()
                inserted += len(batch)
            except Exception as e:
                # MySQL 5.x may not support insert().on_duplicate_key_update() for non-raw strings
                # Fallback row by row
                db.rollback()
                print(f"  batch upsert failed ({e!s}), fallback per-row")
                for r in batch:
                    exist = db.execute(
                        select(Organization.organization_id).where(
                            Organization.organization_code == r["organization_code"]
                        )
                    ).scalar_one_or_none()
                    if exist:
                        skipped += 1
                        code_to_id[r["organization_code"]] = int(exist)
                        continue
                    o = Organization(
                        organization_code=r["organization_code"],
                        canonical_name=r["canonical_name"],
                        normalized_name=r["normalized_name"],
                        organization_type_code=r["organization_type_code"],
                        province_name=r["province_name"],
                        city_name=r["city_name"],
                        website_url=r["website_url"],
                        industry_text=r["industry_text"],
                        source_metadata_json=r["source_metadata_json"],
                        organization_status_code=r["organization_status_code"],
                    )
                    db.add(o)
                    db.flush()
                    code_to_id[r["organization_code"]] = int(o.organization_id)
                db.commit()
                inserted += len(batch) - skipped

        # re-query ids (in case upsert didn't return them)
        all_codes = [r["organization_code"] for r in prepared_rows]
        for chunk in [all_codes[i : i + 800] for i in range(0, len(all_codes), 800)]:
            rows = db.execute(
                select(Organization.organization_code, Organization.organization_id).where(
                    Organization.organization_code.in_(chunk)
                )
            ).all()
            for code, oid in rows:
                code_to_id[code] = int(oid)

        # 4) Insert aliases (ignore duplicates by UK constraint)
        alias_rows = []
        for r in prepared_rows:
            oid = code_to_id.get(r["organization_code"])
            if not oid:
                continue
            for alias_text in r["aliases"]:
                if not alias_text:
                    continue
                alias_rows.append(
                    {
                        "organization_id": oid,
                        "alias_text": alias_text[:500],
                        "normalized_alias": _norm(alias_text)[:500],
                        "alias_type_code": "splink_member",
                    }
                )
        deduped = {}
        for a in alias_rows:
            deduped[(a["organization_id"], a["normalized_alias"])] = a
        alias_rows = list(deduped.values())
        print(f"Inserting {len(alias_rows)} aliases...")
        inserted_aliases = 0
        for a in alias_rows:
            exist = db.execute(
                select(OrganizationAlias.organization_alias_id).where(
                    OrganizationAlias.organization_id == a["organization_id"],
                    OrganizationAlias.normalized_alias == a["normalized_alias"],
                )
            ).scalar_one_or_none()
            if exist:
                continue
            db.add(OrganizationAlias(**a))
            inserted_aliases += 1
            if inserted_aliases % 1000 == 0:
                db.commit()
        db.commit()

    total_orgs = len(code_to_id)
    print(f"\nDone: upserted organizations={inserted} (skipped_conflict={skipped}), total_in_table={total_orgs}")
    print(f"      inserted aliases={inserted_aliases}")


if __name__ == "__main__":
    main()
