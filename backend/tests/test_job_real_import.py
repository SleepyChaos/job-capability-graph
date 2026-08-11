from datetime import date, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.ingestion.service import WorkbookStagingService
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

        assert first.total_jobs == 3718
        assert first.organization_count == 84
        assert first.unique_content_count == 3391
        assert first.duplicate_group_count == 235
        assert first.duplicate_member_count == 562
        assert first.source_timed_count == 1691
        assert first.migration_timed_count == 2027
        assert first.technology_covered_job_count == 1678
        assert first.requirement_count == 4880
        assert first.evidence_span_count == 7591
        assert not first.already_published
        assert second.already_published

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
        finally:
            app.dependency_overrides.clear()

        assert summary.status_code == 200
        assert summary.json()["total_jobs"] == 3718
        assert summary.json()["technology_covered_job_count"] == 1678
        assert duplicates.status_code == 200
        assert duplicates.json()["total"] == 562
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
