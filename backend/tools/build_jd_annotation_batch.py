from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.job.models import (
    JobClusterFeatureSnapshot,
    JobParseResult,
    JobParseRun,
    JobPosting,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成JD解析人工标注候选清单。")
    parser.add_argument("--run-code")
    parser.add_argument("--sample-count", type=int, default=120)
    parser.add_argument("--per-domain-min", type=int, default=10)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def stable_order(job_code: str) -> str:
    return hashlib.sha256(f"jd_annotation_v1\0{job_code}".encode()).hexdigest()


def primary_domain(feature: JobClusterFeatureSnapshot) -> str:
    return (
        max(feature.domain_weights_json, key=feature.domain_weights_json.get)
        if feature.domain_weights_json
        else "UNCLASSIFIED"
    )


def main() -> None:
    args = parse_args()
    if args.sample_count < args.per_domain_min * 7:
        raise SystemExit("样本总数不足以满足T1-T7最低覆盖")
    with SessionLocal() as session:
        run_query = select(JobParseRun)
        if args.run_code:
            run_query = run_query.where(JobParseRun.run_code == args.run_code)
        else:
            run_query = run_query.order_by(
                JobParseRun.completed_at.desc(), JobParseRun.job_parse_run_id.desc()
            )
        run = session.scalar(run_query.limit(1))
        if run is None:
            raise SystemExit("找不到JD解析运行")
        rows = list(
            session.execute(
                select(JobPosting, JobParseResult, JobClusterFeatureSnapshot)
                .join(
                    JobParseResult,
                    JobParseResult.job_posting_id == JobPosting.job_posting_id,
                )
                .join(
                    JobClusterFeatureSnapshot,
                    JobClusterFeatureSnapshot.job_posting_id == JobPosting.job_posting_id,
                )
                .where(
                    JobParseResult.job_parse_run_id == run.job_parse_run_id,
                    JobClusterFeatureSnapshot.job_parse_run_id == run.job_parse_run_id,
                    JobClusterFeatureSnapshot.eligible_for_clustering.is_(True),
                )
            ).all()
        )
        by_domain: dict[str, list[tuple]] = defaultdict(list)
        for row in rows:
            domain = primary_domain(row[2])
            by_domain[domain].append(row)
        for values in by_domain.values():
            values.sort(key=lambda row: stable_order(row[0].job_code))
        selected: list[tuple] = []
        selected_ids: set[int] = set()
        for domain in [f"T{index}" for index in range(1, 8)]:
            candidates = by_domain.get(domain, [])
            if len(candidates) < args.per_domain_min:
                raise SystemExit(f"{domain}只有{len(candidates)}条候选，不满足最低覆盖")
            for row in candidates[: args.per_domain_min]:
                selected.append(row)
                selected_ids.add(row[0].job_posting_id)
        remaining = sorted(
            (row for row in rows if row[0].job_posting_id not in selected_ids),
            key=lambda row: (
                not row[1].review_required,
                stable_order(row[0].job_code),
            ),
        )
        selected.extend(remaining[: args.sample_count - len(selected)])
        samples = []
        for index, (job, parse_result, feature) in enumerate(selected, start=1):
            samples.append(
                {
                    "sample_id": f"jd_annotation_{index:04d}",
                    "job_code": job.job_code,
                    "source_job_id": job.source_job_id,
                    "content_hash": parse_result.content_hash,
                    "primary_domain": primary_domain(feature),
                    "job_level": job.job_level_code,
                    "time_quality": job.time_quality_code,
                    "parse_quality_score": float(parse_result.parse_quality_score),
                    "review_reasons": (parse_result.reason_json or {}).get("reasons", []),
                    "annotation_status": "pending_double_annotation",
                }
            )
        distribution = Counter(item["primary_domain"] for item in samples)
        output = {
            "dataset_id": "jd_parsing_annotation_candidates_v1",
            "schema_version": "jd_gold_schema_v1",
            "status": "candidate_not_gold",
            "parse_run_code": run.run_code,
            "input_snapshot_hash": run.input_snapshot_hash,
            "sample_count": len(samples),
            "selection_method": "deterministic_stratified_t_domain_with_review_hard_cases",
            "domain_distribution": dict(sorted(distribution.items())),
            "warning": "候选清单必须经过双人标注与裁决后才能冻结为金标准。",
            "samples": samples,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: output[key] for key in output if key != "samples"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
