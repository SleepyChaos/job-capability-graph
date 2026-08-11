from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.modules.job.models import (
    EvidenceSpan,
    JobClusterFeatureSnapshot,
    JobFactEvidence,
    JobParseResult,
    JobParseRun,
    JobPosting,
    JobResponsibility,
    SourceDocumentVersion,
    TechnologyAmbiguityRule,
    TechnologyMatchAssessment,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="验证JD结构化解析证据和聚类特征。")
    parser.add_argument("--run-code")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def count(session, model, *conditions) -> int:
    statement = select(func.count()).select_from(model)
    if conditions:
        statement = statement.where(*conditions)
    return session.scalar(statement) or 0


def feature_hash(feature: JobClusterFeatureSnapshot) -> str:
    payload = {
        "title_tokens": feature.title_tokens_json,
        "responsibility_tokens": feature.responsibility_tokens_json,
        "technology_weights": feature.technology_weights_json,
        "domain_weights": feature.domain_weights_json,
        "level_code": feature.level_code,
        "sample_weight": float(feature.sample_weight),
        "time_quality_code": feature.time_quality_code,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def main() -> None:
    args = parse_args()
    with SessionLocal() as session:
        query = select(JobParseRun)
        if args.run_code:
            query = query.where(JobParseRun.run_code == args.run_code)
        else:
            query = query.order_by(
                JobParseRun.completed_at.desc(), JobParseRun.job_parse_run_id.desc()
            )
        run = session.scalar(query.limit(1))
        if run is None:
            raise SystemExit("找不到JD解析运行")
        run_id = run.job_parse_run_id
        parse_status = dict(
            session.execute(
                select(JobParseResult.parse_status_code, func.count())
                .where(JobParseResult.job_parse_run_id == run_id)
                .group_by(JobParseResult.parse_status_code)
            ).all()
        )
        assessment_status = dict(
            session.execute(
                select(TechnologyMatchAssessment.assessment_status_code, func.count())
                .where(TechnologyMatchAssessment.job_parse_run_id == run_id)
                .group_by(TechnologyMatchAssessment.assessment_status_code)
            ).all()
        )
        ambiguity_by_alias = {
            alias: total
            for alias, total in session.execute(
                select(TechnologyAmbiguityRule.normalized_alias, func.count())
                .join(
                    TechnologyMatchAssessment,
                    TechnologyMatchAssessment.ambiguity_rule_id
                    == TechnologyAmbiguityRule.technology_ambiguity_rule_id,
                )
                .where(
                    TechnologyMatchAssessment.job_parse_run_id == run_id,
                    TechnologyMatchAssessment.assessment_status_code == "needs_review",
                )
                .group_by(TechnologyAmbiguityRule.normalized_alias)
                .order_by(func.count().desc())
            ).all()
        }
        bad_offsets = (
            session.scalar(
                select(func.count())
                .select_from(EvidenceSpan)
                .join(
                    SourceDocumentVersion,
                    SourceDocumentVersion.source_document_version_id
                    == EvidenceSpan.source_document_version_id,
                )
                .where(
                    EvidenceSpan.span_type_code.in_(["responsibility", "requirement_context"]),
                    func.substr(
                        SourceDocumentVersion.content_text,
                        EvidenceSpan.start_offset + 1,
                        EvidenceSpan.end_offset - EvidenceSpan.start_offset,
                    )
                    != EvidenceSpan.evidence_text,
                )
            )
            or 0
        )
        features = list(
            session.scalars(
                select(JobClusterFeatureSnapshot).where(
                    JobClusterFeatureSnapshot.job_parse_run_id == run_id
                )
            )
        )
        invalid_feature_hashes = sum(item.feature_hash != feature_hash(item) for item in features)
        invalid_domain_codes = sum(
            any(
                code not in {f"T{index}" for index in range(1, 8)}
                for code in item.domain_weights_json
            )
            for item in features
        )
        primary_domains = Counter(
            max(item.domain_weights_json, key=item.domain_weights_json.get)
            for item in features
            if item.domain_weights_json
        )
        report = {
            "schema_version": "1.0",
            "run": {
                "run_code": run.run_code,
                "parser_version": run.parser_version,
                "target_date": run.target_date.isoformat(),
                "input_snapshot_hash": run.input_snapshot_hash,
                "status": run.run_status_code,
            },
            "counts": {
                "input_jobs": run.input_job_count,
                "parse_results": count(
                    session, JobParseResult, JobParseResult.job_parse_run_id == run_id
                ),
                "responsibilities": count(
                    session, JobResponsibility, JobResponsibility.job_parse_run_id == run_id
                ),
                "responsibility_evidence_links": count(
                    session, JobFactEvidence, JobFactEvidence.job_parse_run_id == run_id
                ),
                "technology_assessments": count(
                    session,
                    TechnologyMatchAssessment,
                    TechnologyMatchAssessment.job_parse_run_id == run_id,
                ),
                "cluster_features": len(features),
                "eligible_cluster_features": sum(item.eligible_for_clustering for item in features),
                "excluded_cluster_features": sum(
                    not item.eligible_for_clustering for item in features
                ),
                "jobs_with_source_time": count(
                    session,
                    JobPosting,
                    JobPosting.time_quality_code == "source_collected",
                ),
            },
            "parse_status": parse_status,
            "assessment_status": assessment_status,
            "ambiguity_reviews_by_alias": ambiguity_by_alias,
            "primary_domain_distribution": dict(sorted(primary_domains.items())),
            "quality": {
                "average_parse_quality": round(
                    float(
                        session.scalar(
                            select(func.avg(JobParseResult.parse_quality_score)).where(
                                JobParseResult.job_parse_run_id == run_id
                            )
                        )
                        or 0
                    ),
                    2,
                ),
                "bad_evidence_offsets": bad_offsets,
                "invalid_feature_hashes": invalid_feature_hashes,
                "invalid_domain_codes": invalid_domain_codes,
            },
            "checks": {
                "all_jobs_have_parse_result": count(
                    session, JobParseResult, JobParseResult.job_parse_run_id == run_id
                )
                == run.input_job_count,
                "all_jobs_have_feature_snapshot": len(features) == run.input_job_count,
                "all_responsibilities_have_evidence": count(
                    session, JobResponsibility, JobResponsibility.job_parse_run_id == run_id
                )
                == count(session, JobFactEvidence, JobFactEvidence.job_parse_run_id == run_id),
                "all_technology_evidence_assessed": count(
                    session,
                    TechnologyMatchAssessment,
                    TechnologyMatchAssessment.job_parse_run_id == run_id,
                )
                == 7591,
            },
        }
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
