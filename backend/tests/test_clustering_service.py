from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.modules.clustering.models import (
    JobClusteringRun,
    JobClusterMember,
    JobRole,
    JobRoleVersion,
    JobRoleVersionRequirement,
)
from app.modules.clustering.service import run_full_clustering
from app.modules.data_center.models import ReviewTask
from app.modules.job.models import (
    DataSource,
    EvidenceSpan,
    JobClusterFeatureSnapshot,
    JobParseRun,
    JobPosting,
    JobPostingDataSource,
    JobRequirement,
    JobResponsibility,
    Organization,
    SourceDocument,
    SourceDocumentVersion,
    TechnologyMatchAssessment,
)
from app.modules.taxonomy.models import (
    TechnologyDomain,
    TechnologyNode,
    TechnologyTaxonomyVersion,
)


def test_clustering_service_builds_replayable_role_candidate() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        parse_run_code = _seed_cluster_fixture(session)

        result = run_full_clustering(session, parse_run_code=parse_run_code)
        repeated = run_full_clustering(session, parse_run_code=parse_run_code)

        assert result.already_completed is False
        assert repeated.already_completed is True
        assert repeated.run_code == result.run_code
        assert result.input_job_count == 4
        assert result.cluster_count == 2
        assert result.candidate_role_count == 1
        assert session.scalar(select(func.count()).select_from(JobClusterMember)) == 4
        assert session.scalar(select(func.count()).select_from(JobRole)) == 1
        version = session.scalar(select(JobRoleVersion))
        assert version is not None and version.approval_status_code == "pending"
        requirement = session.scalar(select(JobRoleVersionRequirement))
        assert requirement is not None
        assert requirement.trend_status_code == "insufficient_history"
        assert session.scalar(select(func.count()).select_from(ReviewTask)) == 1
        run = session.scalar(select(JobClusteringRun))
        assert (
            run is not None
            and run.quality_metric_json["scenario_feature_status"] == "not_available"
        )


def _seed_cluster_fixture(session: Session) -> str:
    taxonomy = TechnologyTaxonomyVersion(
        version_code="cluster-test-v1",
        version_name="聚类合成技术体系",
        source_file_asset_id=1,
        effective_date=date(2026, 8, 1),
        version_status_code="active",
    )
    source = DataSource(
        source_code="CLUSTER-SYNTH",
        source_name="聚类合成来源",
        source_type_code="recruitment",
        content_type_code="job",
        default_reliability_score=Decimal("90"),
    )
    organizations = [
        Organization(
            organization_code="ORG-A",
            canonical_name="合成企业A",
            normalized_name="合成企业a",
        ),
        Organization(
            organization_code="ORG-B",
            canonical_name="合成企业B",
            normalized_name="合成企业b",
        ),
    ]
    session.add_all([taxonomy, source, *organizations])
    session.flush()
    technology = TechnologyNode(
        taxonomy_version_id=taxonomy.taxonomy_version_id,
        technology_code="SYNTH-T1-L3",
        source_spreadsheet_row_id=1,
        level_code="L3",
        technology_name="合成机器人控制",
        normalized_name="合成机器人控制",
    )
    domain = TechnologyDomain(
        source_spreadsheet_row_id=1,
        domain_version="cluster-test-v1",
        domain_code="T1",
        domain_name="合成智能域",
        sort_order=1,
    )
    session.add_all([technology, domain])
    session.flush()
    parse_run = JobParseRun(
        run_code="PARSE-CLUSTER-SYNTH",
        parser_version="synthetic-v1",
        taxonomy_version_id=taxonomy.taxonomy_version_id,
        target_date=date(2026, 8, 10),
        input_snapshot_hash="a" * 64,
        run_status_code="completed",
        input_job_count=4,
        parsed_job_count=4,
        feature_count=4,
    )
    session.add(parse_run)
    session.flush()

    for index in range(4):
        similar = index < 3
        title = "机器人控制算法工程师" if similar else "供应链采购专员"
        content = "负责机器人控制算法开发" if similar else "负责供应商采购管理"
        document = SourceDocument(
            document_code=f"DOC-CLUSTER-{index}",
            data_source_id=source.data_source_id,
            document_type_code="job",
            source_record_key=f"job-{index}",
            canonical_url=f"https://example.invalid/jobs/{index}",
            document_identity_key=f"{index:064d}",
            title=title,
            first_seen_at=datetime(2026, 7, 16),
            last_seen_at=datetime(2026, 7, 16),
        )
        session.add(document)
        session.flush()
        document_version = SourceDocumentVersion(
            source_document_id=document.source_document_id,
            version_no=1,
            collected_at=datetime(2026, 7, 16),
            source_collected_at=datetime(2026, 7, 16),
            valid_from=datetime(2026, 7, 16),
            content_text=content,
            content_hash=f"{index + 10:064d}",
        )
        session.add(document_version)
        session.flush()
        job = JobPosting(
            job_code=f"JOB-CLUSTER-{index}",
            source_document_version_id=document_version.source_document_version_id,
            data_source_id=source.data_source_id,
            organization_id=organizations[index % 2].organization_id,
            company_name_raw=organizations[index % 2].canonical_name,
            job_title_raw=title,
            job_title_normalized=title,
            job_level_code="middle",
            jd_clean_text=content,
            collected_at=datetime(2026, 7, 16),
            source_collected_at=datetime(2026, 7, 16),
            time_quality_code="source_collected",
            evidence_weight=Decimal("1"),
        )
        session.add(job)
        session.flush()
        session.add(
            JobPostingDataSource(
                job_posting_id=job.job_posting_id,
                data_source_id=source.data_source_id,
                source_role_code="primary",
                source_order=1,
            )
        )
        if similar:
            requirement = JobRequirement(
                job_posting_id=job.job_posting_id,
                requirement_no=1,
                requirement_type_code="required",
                raw_term="合成机器人控制",
                raw_text="要求掌握合成机器人控制",
                technology_node_id=technology.technology_node_id,
                mention_count=1,
                confidence_score=Decimal("95"),
            )
            session.add(requirement)
            session.flush()
            evidence = EvidenceSpan(
                source_document_version_id=document_version.source_document_version_id,
                span_type_code="requirement",
                evidence_text="要求掌握合成机器人控制",
                evidence_hash=f"{index + 30:064d}",
                source_reliability_score=Decimal("90"),
            )
            session.add(evidence)
            session.flush()
            session.add(
                TechnologyMatchAssessment(
                    job_parse_run_id=parse_run.job_parse_run_id,
                    job_requirement_id=requirement.job_requirement_id,
                    evidence_span_id=evidence.evidence_span_id,
                    context_type_code="technical",
                    assessment_status_code="accepted",
                    adjusted_support_score=Decimal("95"),
                    feature_weight=Decimal("1"),
                    reason_code="synthetic_accepted",
                )
            )
        session.add(
            JobResponsibility(
                job_parse_run_id=parse_run.job_parse_run_id,
                job_posting_id=job.job_posting_id,
                responsibility_no=1,
                raw_text=content,
                normalized_task_text=content,
                extraction_method_code="synthetic",
                confidence_score=Decimal("95"),
            )
        )
        session.add(
            JobClusterFeatureSnapshot(
                job_parse_run_id=parse_run.job_parse_run_id,
                job_posting_id=job.job_posting_id,
                feature_version="cluster_features_v1",
                title_tokens_json=(["机器人", "控制", "算法"] if similar else ["供应链", "采购"]),
                responsibility_tokens_json=(
                    ["机器人", "控制", "开发"] if similar else ["供应商", "采购", "管理"]
                ),
                technology_weights_json=({"SYNTH-T1-L3": 1.0} if similar else {}),
                domain_weights_json=({"T1": 1.0} if similar else {}),
                level_code="middle",
                sample_weight=Decimal("1"),
                time_quality_code="source_collected",
                feature_hash=f"{index + 20:064d}",
            )
        )
    session.commit()
    return parse_run.run_code
