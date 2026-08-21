from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.graph.models import TripleContradictionAssessment

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "data" / "evaluation" / "layer_c" / "annotation_batches_v1"


def stable_key(row: TripleContradictionAssessment) -> str:
    value = f"{row.subject_kind}|{row.subject_id}|{row.predicate}|{row.object_kind}|{row.object_id}"
    return hashlib.sha256(value.encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-run-code", required=True)
    parser.add_argument("--per-level", type=int, default=50)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    with SessionLocal() as db:
        all_rows = list(db.scalars(select(TripleContradictionAssessment).where(TripleContradictionAssessment.audit_run_code == args.audit_run_code)))
    selected = []
    for level in ("low", "medium", "high"):
        candidates = sorted((row for row in all_rows if row.plausibility_level == level), key=stable_key)
        if len(candidates) < args.per_level:
            raise SystemExit(f"{level}仅{len(candidates)}条，不足{args.per_level}条")
        selected.extend(candidates[: args.per_level])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    fields = [
        "sample_id", "audit_run_code", "stratum", "subject_kind", "subject_id", "subject_label",
        "predicate", "object_kind", "object_id", "object_label", "plausibility_score",
        "supporting_job_count", "support_percentile", "jaccard", "path_closure",
        "label", "evidence_checked", "annotator", "note",
    ]
    base_rows = []
    for index, row in enumerate(selected, 1):
        components = row.component_scores or {}
        evidence = row.evidence_summary_json or {}
        base_rows.append({
            "sample_id": f"layer_c_{index:04d}", "audit_run_code": row.audit_run_code,
            "stratum": row.plausibility_level, "subject_kind": row.subject_kind,
            "subject_id": row.subject_id, "subject_label": row.subject_label,
            "predicate": row.predicate, "object_kind": row.object_kind,
            "object_id": row.object_id, "object_label": row.object_label,
            "plausibility_score": float(row.plausibility_score),
            "supporting_job_count": evidence.get("supporting_job_count", 0),
            "support_percentile": components.get("support", 0), "jaccard": components.get("jaccard", 0),
            "path_closure": components.get("path_closure", 0), "label": "",
            "evidence_checked": "false", "annotator": "", "note": "",
        })
    for name in ("annotator_A.csv", "annotator_B.csv", "adjudicated.csv"):
        with (args.output_dir / name).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader(); writer.writerows(base_rows)
    manifest = {
        "dataset_id": "layer_c_calibration_frozen_v1",
        "status": "frozen_for_double_annotation",
        "audit_run_code": args.audit_run_code,
        "sample_count": len(base_rows),
        "stratum_counts": {level: args.per_level for level in ("low", "medium", "high")},
        "selection": "stable_sha256_within_stratum",
        "annotator_A_sha256": hashlib.sha256((args.output_dir / "annotator_A.csv").read_bytes()).hexdigest(),
        "annotator_B_sha256": hashlib.sha256((args.output_dir / "annotator_B.csv").read_bytes()).hexdigest(),
        "requires_adjudication": True,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"frozen {len(base_rows)} triples from {args.audit_run_code} into {args.output_dir}")


if __name__ == "__main__":
    main()
