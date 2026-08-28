"""Score selected postings for one confirmed profile without truncating to Top-N."""

from __future__ import annotations

import argparse
import json

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.clustering.models import JobClusterMember, JobClusterVersion
from app.modules.graph.service import _cluster_capability_metrics, _context, _signals_by_job
from app.modules.job.models import JobPosting
from app.modules.talent.models import ResumeDocument
from app.modules.talent.service import (
    PostingMatchTarget,
    _get_version,
    _profile_evidence_text,
    _role_relevance_band,
    _role_title_relevance,
    _score_cluster,
    _skills,
)


def diagnose(version_code: str, job_codes: list[str]) -> list[dict]:
    with SessionLocal() as db:
        version = _get_version(db, version_code)
        context = _context(db)
        document = db.get(ResumeDocument, version.resume_document_id)
        resume_text = _profile_evidence_text(
            version,
            document.content_text if document is not None else "",
        )
        profile_skill_map = {
            item.technology_node_id: item
            for item in _skills(db, version.candidate_profile_version_id)
        }
        signals_by_job = _signals_by_job(context.signals)
        output = []
        for job_code in job_codes:
            posting = db.scalar(
                select(JobPosting).where(JobPosting.job_code == job_code)
            )
            if posting is None:
                output.append({"job_code": job_code, "error": "not_found"})
                continue
            cluster = db.scalar(
                select(JobClusterVersion)
                .join(
                    JobClusterMember,
                    JobClusterMember.job_cluster_version_id
                    == JobClusterVersion.job_cluster_version_id,
                )
                .where(
                    JobClusterMember.job_posting_id == posting.job_posting_id,
                    JobClusterVersion.clustering_run_id
                    == context.run.clustering_run_id,
                )
            )
            target = cluster or PostingMatchTarget(
                job_cluster_version_id=None,
                stable_cluster_code=f"unclustered:{posting.job_code}",
                cluster_label=posting.job_title_normalized or posting.job_title_raw,
            )
            member_ids = {posting.job_posting_id}
            metrics = _cluster_capability_metrics(
                context,
                target,
                member_ids,
                signals_by_job,
                level_code="L3",
                recent_job_count=10,
            )[:20]
            result = _score_cluster(
                db,
                context.nodes,
                version,
                target,
                metrics,
                member_ids,
                profile_skill_map,
                reference_date=context.run.target_date,
                resume_text=resume_text,
            )
            role_relevance = _role_title_relevance(
                version.target_role_text,
                posting.job_title_normalized or posting.job_title_raw,
            )
            output.append(
                {
                    "job_code": posting.job_code,
                    "title": posting.job_title_raw,
                    "company": posting.company_name_raw,
                    "overall_score": result["overall_score"],
                    "role_relevance": role_relevance,
                    "role_relevance_band": _role_relevance_band(role_relevance),
                    "dimensions": result["dimensions"],
                    "score_interval": result["score_interval"],
                }
            )
        return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("version_code")
    parser.add_argument("job_codes", nargs="+")
    args = parser.parse_args()
    print(json.dumps(diagnose(args.version_code, args.job_codes), ensure_ascii=False))


if __name__ == "__main__":
    main()
