from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.modules.ingestion.models import FileImportRun, RawFileAsset
from app.modules.job.models import (
    DataSource,
    DocumentQuality,
    DuplicateDocumentGroup,
    DuplicateDocumentMember,
    EvidenceSpan,
    JobPosting,
    JobPostingDataSource,
    JobRequirement,
    JobRequirementEvidence,
    Organization,
    OrganizationAlias,
    SourceDocument,
    SourceDocumentVersion,
)
from app.modules.taxonomy.models import TechnologyAlias, TechnologyNode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="验证JD全量导入数量、证据和去重权重。")
    parser.add_argument("--mapping-code", required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def scalar_count(session, model, *conditions) -> int:
    statement = select(func.count()).select_from(model)
    if conditions:
        statement = statement.where(*conditions)
    return session.scalar(statement) or 0


def main() -> None:
    args = parse_args()
    with SessionLocal() as session:
        import_run = session.scalar(
            select(FileImportRun)
            .where(FileImportRun.mapping_code == args.mapping_code)
            .order_by(FileImportRun.created_at.desc())
            .limit(1)
        )
        if import_run is None:
            raise SystemExit(f"找不到映射{args.mapping_code}对应的导入运行")
        asset = session.get(RawFileAsset, import_run.file_asset_id)
        if asset is None:
            raise SystemExit("导入运行缺少文件资产")

        quality_status = dict(
            session.execute(
                select(DocumentQuality.quality_status_code, func.count()).group_by(
                    DocumentQuality.quality_status_code
                )
            ).all()
        )
        time_quality = dict(
            session.execute(
                select(JobPosting.time_quality_code, func.count()).group_by(
                    JobPosting.time_quality_code
                )
            ).all()
        )
        source_memberships = dict(
            session.execute(
                select(DataSource.source_code, func.count())
                .join(
                    JobPostingDataSource,
                    JobPostingDataSource.data_source_id == DataSource.data_source_id,
                )
                .group_by(DataSource.source_code)
            ).all()
        )
        top_technologies = [
            {
                "technology_code": code,
                "technology_name": name,
                "job_count": job_count,
                "mention_count": mention_count,
            }
            for code, name, job_count, mention_count in session.execute(
                select(
                    TechnologyNode.technology_code,
                    TechnologyNode.technology_name,
                    func.count(func.distinct(JobRequirement.job_posting_id)),
                    func.sum(JobRequirement.mention_count),
                )
                .join(
                    JobRequirement,
                    JobRequirement.technology_node_id == TechnologyNode.technology_node_id,
                )
                .group_by(TechnologyNode.technology_node_id)
                .order_by(func.count(func.distinct(JobRequirement.job_posting_id)).desc())
                .limit(15)
            ).all()
        ]
        top_matched_aliases = [
            {
                "alias": alias_text,
                "source_type": source_type,
                "evidence_count": evidence_count,
            }
            for alias_text, source_type, evidence_count in session.execute(
                select(
                    TechnologyAlias.alias_text,
                    TechnologyAlias.source_type_code,
                    func.count(),
                )
                .join(
                    JobRequirementEvidence,
                    JobRequirementEvidence.matched_alias_id == TechnologyAlias.technology_alias_id,
                )
                .group_by(TechnologyAlias.technology_alias_id)
                .order_by(func.count().desc())
                .limit(20)
            ).all()
        ]
        bad_evidence_offsets = (
            session.scalar(
                select(func.count())
                .select_from(EvidenceSpan)
                .join(
                    SourceDocumentVersion,
                    SourceDocumentVersion.source_document_version_id
                    == EvidenceSpan.source_document_version_id,
                )
                .where(
                    func.substr(
                        SourceDocumentVersion.content_text,
                        EvidenceSpan.start_offset + 1,
                        EvidenceSpan.end_offset - EvidenceSpan.start_offset,
                    )
                    != EvidenceSpan.evidence_text
                )
            )
            or 0
        )
        duplicate_weight_sums = (
            select(
                DuplicateDocumentMember.duplicate_group_id,
                func.sum(JobPosting.evidence_weight).label("weight_sum"),
            )
            .join(
                JobPosting,
                JobPosting.source_document_version_id
                == DuplicateDocumentMember.source_document_version_id,
            )
            .group_by(DuplicateDocumentMember.duplicate_group_id)
            .subquery()
        )
        duplicate_weight_mismatches = (
            session.scalar(
                select(func.count())
                .select_from(duplicate_weight_sums)
                .where(func.round(duplicate_weight_sums.c.weight_sum, 6) != 1)
            )
            or 0
        )
        report = {
            "schema_version": "1.0",
            "source": {
                "file_name": asset.original_file_name,
                "sha256": asset.sha256_hash,
                "mapping_code": import_run.mapping_code,
                "mapping_version": import_run.mapping_version,
                "schema_hash": import_run.source_schema_hash,
            },
            "counts": {
                "jobs": scalar_count(session, JobPosting),
                "organizations": scalar_count(session, Organization),
                "organization_aliases": scalar_count(session, OrganizationAlias),
                "data_sources": scalar_count(session, DataSource),
                "source_documents": scalar_count(session, SourceDocument),
                "document_versions": scalar_count(session, SourceDocumentVersion),
                "unique_content": session.scalar(
                    select(func.count(func.distinct(SourceDocumentVersion.content_hash)))
                )
                or 0,
                "duplicate_groups": scalar_count(session, DuplicateDocumentGroup),
                "duplicate_members": scalar_count(session, DuplicateDocumentMember),
                "technology_covered_jobs": session.scalar(
                    select(func.count(func.distinct(JobRequirement.job_posting_id)))
                )
                or 0,
                "requirements": scalar_count(session, JobRequirement),
                "evidence_spans": scalar_count(session, EvidenceSpan),
                "matchable_aliases": scalar_count(
                    session, TechnologyAlias, TechnologyAlias.is_matchable.is_(True)
                ),
                "missing_organization_jobs": scalar_count(
                    session, JobPosting, JobPosting.organization_id.is_(None)
                ),
                "missing_or_invalid_url_documents": scalar_count(
                    session, SourceDocument, SourceDocument.canonical_url.is_(None)
                ),
            },
            "quality_status": quality_status,
            "time_quality": time_quality,
            "source_memberships": source_memberships,
            "top_technologies": top_technologies,
            "top_matched_aliases": top_matched_aliases,
            "checks": {
                "bad_evidence_offsets": bad_evidence_offsets,
                "duplicate_weight_sum_mismatches": duplicate_weight_mismatches,
                "expected_job_count": scalar_count(session, JobPosting) == 3718,
                "expected_unique_content_count": (
                    session.scalar(
                        select(func.count(func.distinct(SourceDocumentVersion.content_hash)))
                    )
                    == 3391
                ),
                "expected_duplicate_group_count": (
                    scalar_count(session, DuplicateDocumentGroup) == 235
                ),
            },
        }
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
