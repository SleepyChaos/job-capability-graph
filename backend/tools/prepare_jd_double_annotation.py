from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.job.models import JobPosting

ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = ROOT / "data" / "evaluation" / "jd_parsing"
EXPECTED_SHA256 = "52c0859895d8916e3a770cfd6fdc3f649a696cc3394855bffe4386f748ef1bbe"


def blank_annotation() -> dict:
    return {
        "job_title": [],
        "responsibilities": [],
        "required_skills": [],
        "bonus_skills": [],
        "application_scenarios": [],
        "quality_flags": [],
        "annotator_note": "",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=EVAL_DIR / "annotation_batches_v1")
    args = parser.parse_args()
    source = EVAL_DIR / "annotation_candidates_v1.json"
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_SHA256:
        raise SystemExit(f"候选清单哈希变化，拒绝生成：{digest}")
    manifest = json.loads(raw)
    if manifest.get("sample_count") != 120 or len(manifest.get("samples", [])) != 120:
        raise SystemExit("冻结集必须恰好包含120条样本")
    job_codes = [item["job_code"] for item in manifest["samples"]]
    with SessionLocal() as db:
        jobs = {
            job.job_code: job
            for job in db.scalars(select(JobPosting).where(JobPosting.job_code.in_(job_codes)))
        }
    missing = sorted(set(job_codes) - set(jobs))
    if missing:
        raise SystemExit(f"数据库缺少冻结JD：{missing[:5]}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for sample in manifest["samples"]:
        job = jobs[sample["job_code"]]
        rows.append({
            **sample,
            "job_title_raw": job.job_title_raw,
            "company_name_raw": job.company_name_raw,
            "jd_clean_text": job.jd_clean_text,
            "annotation": blank_annotation(),
        })
    for annotator in ("A", "B"):
        path = args.output_dir / f"annotator_{annotator}.jsonl"
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    adjudication = args.output_dir / "adjudication.jsonl"
    adjudication.write_text("".join(json.dumps({"sample_id": row["sample_id"], "status": "pending", "resolution": blank_annotation(), "reason": ""}, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({"status": "frozen_for_double_annotation", "sample_count": 120, "output_dir": str(args.output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
