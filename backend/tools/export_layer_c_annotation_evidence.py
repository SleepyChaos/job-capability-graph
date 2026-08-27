from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from sqlalchemy import desc, select

from app.db.session import SessionLocal
from app.modules.clustering.models import JobClusterMember, JobClusterVersion
from app.modules.job.models import JobPosting, JobRequirement, Organization
from app.modules.taxonomy.models import TechnologyNode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="为 Layer C 人工真值标注补充可核对的 JD 证据。")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-evidence", type=int, default=3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with args.input.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))

    with SessionLocal() as db:
        latest_run_id = db.scalar(
            select(JobClusterVersion.clustering_run_id)
            .order_by(
                JobClusterVersion.clustering_run_id.desc(),
                JobClusterVersion.job_cluster_version_id.desc(),
            )
            .limit(1)
        )
        output_rows: list[dict] = []
        for row in rows:
            technology_ids = list(
                db.scalars(
                    select(TechnologyNode.technology_node_id).where(
                        TechnologyNode.technology_code == row["object_id"]
                    )
                )
            )
            query = select(
                JobPosting.job_code,
                JobPosting.source_job_id,
                JobPosting.job_title_raw,
                JobPosting.company_name_raw,
                JobRequirement.requirement_type_code,
                JobRequirement.raw_term,
                JobRequirement.raw_text,
                JobRequirement.confidence_score,
            ).join(JobRequirement, JobRequirement.job_posting_id == JobPosting.job_posting_id)

            if row["subject_kind"] == "cluster":
                query = (
                    query.join(
                        JobClusterMember,
                        JobClusterMember.job_posting_id == JobPosting.job_posting_id,
                    )
                    .join(
                        JobClusterVersion,
                        JobClusterVersion.job_cluster_version_id
                        == JobClusterMember.job_cluster_version_id,
                    )
                    .where(
                        JobClusterVersion.clustering_run_id == latest_run_id,
                        JobClusterVersion.stable_cluster_code == row["subject_id"],
                    )
                )
            elif row["subject_kind"] == "organization":
                query = query.join(
                    Organization, Organization.organization_id == JobPosting.organization_id
                ).where(Organization.organization_code == row["subject_id"])
            else:
                raise SystemExit(f"不支持的主体类型: {row['subject_kind']}")

            if technology_ids:
                query = query.where(JobRequirement.technology_node_id.in_(technology_ids))
            else:
                query = query.where(JobRequirement.job_requirement_id == -1)
            evidence_rows = db.execute(
                query.order_by(desc(JobRequirement.confidence_score), JobPosting.job_posting_id)
            ).all()
            evidence = []
            seen: set[tuple] = set()
            for item in evidence_rows:
                key = (item.job_code, item.requirement_type_code, item.raw_text)
                if key in seen:
                    continue
                seen.add(key)
                evidence.append(
                    {
                        "job_code": item.job_code,
                        "source_job_id": item.source_job_id,
                        "job_title": item.job_title_raw,
                        "company": item.company_name_raw,
                        "requirement_type": item.requirement_type_code,
                        "raw_term": item.raw_term,
                        "evidence_text": item.raw_text,
                        "mapping_confidence": float(item.confidence_score),
                    }
                )
                if len(evidence) >= args.max_evidence:
                    break
            output_rows.append({**row, "evidence": evidence})

    payload = {
        "dataset_id": "layer_c_calibration_annotation_evidence_v1_1",
        "source": str(args.input),
        "sample_count": len(output_rows),
        "latest_clustering_run_id": latest_run_id,
        "max_evidence_per_sample": args.max_evidence,
        "samples": output_rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    missing = sum(not item["evidence"] for item in output_rows)
    print(json.dumps({"sample_count": len(output_rows), "missing_evidence": missing, "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
