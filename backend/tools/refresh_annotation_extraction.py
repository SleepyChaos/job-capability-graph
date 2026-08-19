"""把标注包里的 `current_extraction` 冻结快照刷新到指定解析运行（窗口 C-7 评估链路）。

`evaluate_extraction_quality.py` 是纯离线脚本，对照的是标注包内自带的抽取快照。
要拿同一份标注去评估新版词表，就得先把快照换成新解析运行的结果——**只换预测侧，
`expected_l3_codes` 等人工标注字段逐字保留**，否则版本对比就不成立了。

输出会记录新旧 run_code，便于报告里写清口径。

用法（backend 目录 / 容器内）：
    python -m tools.refresh_annotation_extraction \
        --package /srv/data/annotation/jd_annotation_batch_001.annotator_C.json \
        --parse-run-code jdparse_9130d14a0c3689ee6567c471 \
        --out /srv/data/annotation/jd_annotation_batch_001.annotator_C.v1_2.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.db.session import SessionLocal
from app.modules.job.models import (
    JobParseRun,
    JobPosting,
    JobRequirement,
    JobRequirementEvidence,
    TechnologyMatchAssessment,
)
from app.modules.taxonomy.models import TechnologyAlias, TechnologyNode, TechnologyTaxonomyVersion


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="用指定解析运行刷新标注包的抽取快照。")
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--parse-run-code", required=True)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    package = json.loads(args.package.read_text(encoding="utf-8"))
    job_codes = [sample["job_code"] for sample in package["samples"]]

    with SessionLocal() as session:
        run = session.scalar(select(JobParseRun).where(JobParseRun.run_code == args.parse_run_code))
        if run is None:
            raise SystemExit(f"解析运行不存在：{args.parse_run_code}")
        taxonomy = session.get(TechnologyTaxonomyVersion, run.taxonomy_version_id)
        alias_node = aliased(TechnologyNode)
        rows = session.execute(
            select(
                JobPosting.job_code,
                TechnologyNode.technology_code,
                TechnologyNode.technology_name,
                TechnologyMatchAssessment.assessment_status_code,
                TechnologyAlias.alias_text,
            )
            .join(
                JobRequirement,
                JobRequirement.job_requirement_id == TechnologyMatchAssessment.job_requirement_id,
            )
            .join(JobPosting, JobPosting.job_posting_id == JobRequirement.job_posting_id)
            .join(
                TechnologyNode,
                TechnologyNode.technology_node_id == JobRequirement.technology_node_id,
            )
            .join(
                JobRequirementEvidence,
                (
                    JobRequirementEvidence.job_requirement_id
                    == TechnologyMatchAssessment.job_requirement_id
                )
                & (
                    JobRequirementEvidence.evidence_span_id
                    == TechnologyMatchAssessment.evidence_span_id
                ),
            )
            .join(
                TechnologyAlias,
                TechnologyAlias.technology_alias_id == JobRequirementEvidence.matched_alias_id,
            )
            .outerjoin(
                alias_node, alias_node.technology_node_id == TechnologyAlias.technology_node_id
            )
            .where(
                TechnologyMatchAssessment.job_parse_run_id == run.job_parse_run_id,
                JobPosting.job_code.in_(job_codes),
            )
        ).all()

    # (job_code, L3 代码) → {状态, 命中词集合}；同一技术点多次命中时按最强状态归并。
    grouped: dict[tuple[str, str], dict] = {}
    terms: dict[tuple[str, str], set[str]] = defaultdict(set)
    for job_code, code, name, status, alias_text in rows:
        key = (job_code, code)
        terms[key].add(alias_text)
        entry = grouped.get(key)
        if entry is None:
            grouped[key] = {"technology_code": code, "technology_name": name, "status": status}
        elif entry["status"] != "accepted" and status == "accepted":
            entry["status"] = "accepted"

    by_job: dict[str, list[dict]] = defaultdict(list)
    for (job_code, code), entry in sorted(grouped.items()):
        by_job[job_code].append({**entry, "matched_terms": sorted(terms[(job_code, code)])})

    changed = 0
    for sample in package["samples"]:
        fresh = by_job.get(sample["job_code"], [])
        if fresh != sample.get("current_extraction"):
            changed += 1
        sample["current_extraction"] = fresh
        sample["accepted_cnt"] = sum(1 for item in fresh if item["status"] == "accepted")
        sample["review_cnt"] = sum(1 for item in fresh if item["status"] == "needs_review")

    package["previous_parse_run_code"] = package.get("parse_run_code")
    package["parse_run_code"] = args.parse_run_code
    package["input_snapshot_hash"] = run.input_snapshot_hash
    package["taxonomy_version_code"] = taxonomy.version_code if taxonomy else None
    package["caliber_note"] = (
        f"current_extraction 为 run {args.parse_run_code}"
        f"（词表 {taxonomy.version_code if taxonomy else '?'}）的冻结快照；"
        "expected_l3_codes 等人工标注字段未做任何改动。"
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "out": str(args.out),
                "parse_run_code": args.parse_run_code,
                "taxonomy_version_code": taxonomy.version_code if taxonomy else None,
                "sample_count": len(package["samples"]),
                "changed_sample_count": changed,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
