from datetime import date, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.ingestion.service import WorkbookStagingService
from app.modules.job.models import DuplicateDocumentGroup, DuplicateDocumentMember
from app.modules.job.parsing_service import JobParsingService
from app.modules.job.service import JobImportService
from app.modules.taxonomy.service import TaxonomyImportService


def test_real_job_import_idempotency_and_api() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    taxonomy_path = (
        repository_root / "data" / "source" / "20260810" / "core" / "技术词主数据_20260727.xlsx"
    )
    jobs_path = (
        repository_root / "data" / "source" / "20260810" / "core" / "具身智能岗位_清洗后_v3(1).xlsx"
    )
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        taxonomy_stage = WorkbookStagingService(session).stage(
            taxonomy_path,
            storage_object_key="data/source/20260810/core/技术词主数据_20260727.xlsx",
            importer_code="taxonomy_xlsx_v1",
            mapping_code="technology_taxonomy_20260810",
            mapping_version="1.0.0",
            access_classification="project_internal",
            external_key_fields={
                "L1技术域": "L1编码",
                "L2技术类": "L2编码",
                "L3技术点": "L3编码",
                "L4技术词": "技术词",
            },
        )
        TaxonomyImportService(session).publish(
            file_import_run_id=taxonomy_stage.file_import_run_id,
            version_code="v1.1-job-test",
            version_name="JD集成测试技术体系",
            effective_date=date(2026, 7, 27),
            domain_version="v1.1-job-test",
        )
        job_stage = WorkbookStagingService(session).stage(
            jobs_path,
            storage_object_key="data/source/20260810/core/具身智能岗位_清洗后_v3(1).xlsx",
            importer_code="cleaned_job_xlsx_v1",
            mapping_code="cleaned_job_posting_20260810",
            mapping_version="1.0.0",
            access_classification="project_internal",
            external_key_fields={"岗位数据": "occ_id"},
            include_sheets={"岗位数据"},
        )
        first = JobImportService(session).publish(
            file_import_run_id=job_stage.file_import_run_id,
            taxonomy_version_code="v1.1-job-test",
            received_at=datetime(2026, 8, 10),
        )
        second = JobImportService(session).publish(
            file_import_run_id=job_stage.file_import_run_id,
            taxonomy_version_code="v1.1-job-test",
            received_at=datetime(2026, 8, 10),
        )
        parsing_first = JobParsingService(session).run(
            taxonomy_version_code="v1.1-job-test",
            target_date=date(2026, 8, 10),
        )
        parsing_second = JobParsingService(session).run(
            taxonomy_version_code="v1.1-job-test",
            target_date=date(2026, 8, 10),
        )

        assert first.total_jobs == 3718
        assert first.organization_count == 84
        assert first.unique_content_count == 3391
        # 精确哈希去重保持 235 簇 / 562 成员；SimHash 近重复另计（设计 §6.2）
        exact_groups = session.scalar(
            select(func.count())
            .select_from(DuplicateDocumentGroup)
            .where(DuplicateDocumentGroup.detection_method_code == "exact_content_hash")
        )
        exact_members = session.scalar(
            select(func.count())
            .select_from(DuplicateDocumentMember)
            .join(
                DuplicateDocumentGroup,
                DuplicateDocumentGroup.duplicate_group_id
                == DuplicateDocumentMember.duplicate_group_id,
            )
            .where(DuplicateDocumentGroup.detection_method_code == "exact_content_hash")
        )
        near_groups = session.scalar(
            select(func.count())
            .select_from(DuplicateDocumentGroup)
            .where(DuplicateDocumentGroup.detection_method_code == "simhash_near_duplicate")
        )
        near_members = session.scalar(
            select(func.count())
            .select_from(DuplicateDocumentMember)
            .join(
                DuplicateDocumentGroup,
                DuplicateDocumentGroup.duplicate_group_id
                == DuplicateDocumentMember.duplicate_group_id,
            )
            .where(DuplicateDocumentGroup.detection_method_code == "simhash_near_duplicate")
        )
        assert exact_groups == 235
        assert exact_members == 562
        assert near_groups and near_groups >= 1
        assert first.duplicate_group_count == exact_groups + near_groups
        assert first.duplicate_member_count == exact_members + near_members
        assert first.source_timed_count == 1691
        assert first.migration_timed_count == 2027
        assert first.technology_covered_job_count == 1678
        assert first.requirement_count == 4880
        assert first.evidence_span_count == 7591
        assert not first.already_published
        assert second.already_published
        assert parsing_first.parsed_job_count == 3718
        # 窗口 C-5 起歧义规则升到 v2：语境窗口从整段收紧到同句、检测/汽车/大模型三条规则
        # 退场（对应词形已在 v1.2 下线），需复核的命中因此从 735 降到 126，
        # 连带 review_job_count 从 687 降到 325。基线随规则版本一起更新。
        assert parsing_first.review_job_count == 325
        assert parsing_first.responsibility_count == 16719
        assert parsing_first.assessment_count == 7591
        assert parsing_first.ambiguity_review_count == 126
        assert parsing_first.feature_count == 3718
        assert parsing_first.eligible_feature_count == 3534
        assert not parsing_first.already_completed
        assert parsing_second.already_completed

        def override_db():
            yield session

        app.dependency_overrides[get_db] = override_db
        try:
            with TestClient(app) as client:
                summary = client.get("/api/v1/jobs/summary")
                duplicates = client.get("/api/v1/jobs", params={"duplicate_only": True, "limit": 5})
                ros_jobs = client.get(
                    "/api/v1/jobs",
                    params={"technology_code": "T5.01.01", "limit": 5},
                )
                first_job_code = ros_jobs.json()["items"][0]["job_code"]
                detail = client.get(f"/api/v1/jobs/{first_job_code}")
                parsing_summary = client.get("/api/v1/job-parsing/summary")
                parsing_reviews = client.get(
                    "/api/v1/job-parsing/jobs",
                    params={"review_required": True, "limit": 5},
                )
                parsing_excluded = client.get(
                    "/api/v1/job-parsing/jobs",
                    params={"eligible": False, "limit": 5},
                )
                parsing_detail = client.get(f"/api/v1/job-parsing/jobs/{first_job_code}")
                ambiguity_rules = client.get("/api/v1/job-parsing/ambiguity-rules")
        finally:
            app.dependency_overrides.clear()

        assert summary.status_code == 200
        assert summary.json()["total_jobs"] == 3718
        assert summary.json()["technology_covered_job_count"] == 1678
        assert duplicates.status_code == 200
        assert duplicates.json()["total"] == first.duplicate_member_count
        assert all(item["duplicate_group_code"] for item in duplicates.json()["items"])
        assert ros_jobs.status_code == 200
        assert ros_jobs.json()["total"] == 233
        assert detail.status_code == 200
        assert detail.json()["technologies"]
        assert any(
            technology["technology_code"] == "T5.01.01"
            for technology in detail.json()["technologies"]
        )
        assert all(technology["evidence"] for technology in detail.json()["technologies"])
        assert parsing_summary.status_code == 200
        assert parsing_summary.json()["run"]["parsed_job_count"] == 3718
        assert parsing_summary.json()["ambiguity_review_count"] == 126
        assert parsing_summary.json()["eligible_feature_count"] == 3534
        assert parsing_reviews.status_code == 200
        assert parsing_reviews.json()["total"] == 325
        assert parsing_excluded.status_code == 200
        assert parsing_excluded.json()["total"] == 184
        assert parsing_detail.status_code == 200
        assert parsing_detail.json()["cluster_feature"]["version"] == "cluster_features_v1"
        assert ambiguity_rules.status_code == 200
        # v2 只保留 3 条在用规则（控制系统/多模态大模型/基础模型）；检测/汽车/大模型三条
        # 已随词形下线而退场（存量库里的旧行会被停用，全新库直接不建）。
        assert sum(item["active"] for item in ambiguity_rules.json()) == 3
        assert {item["context_scope"] for item in ambiguity_rules.json() if item["active"]} == {
            "sentence"
        }
