from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.ingestion.service import WorkbookStagingService
from app.modules.job.institution_import import InstitutionImportService


def test_real_institution_import_is_idempotent_and_queryable() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    workbook_path = (
        repository_root
        / "data"
        / "source"
        / "20260810"
        / "restricted"
        / "科技人才库与机构库_20260731.xlsx"
    )
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        stage = WorkbookStagingService(session).stage(
            workbook_path,
            storage_object_key=(
                "data/source/20260810/restricted/科技人才库与机构库_20260731.xlsx"
            ),
            importer_code="institution_xlsx_v1",
            mapping_code="institution_20260810_v1",
            mapping_version="1.0.0",
            access_classification="restricted",
            external_key_fields={"机构库": "机构ID"},
            include_sheets={"机构库"},
        )
        first = InstitutionImportService(session).publish(
            file_import_run_id=stage.file_import_run_id
        )
        second = InstitutionImportService(session).publish(
            file_import_run_id=stage.file_import_run_id
        )
        assert first.source_row_count == 1598
        assert first.created_count + first.merged_count == 1598
        assert first.failed_count == 0
        assert first.total_organization_count >= 1590
        assert not first.already_published
        assert second.already_published
        assert second.total_organization_count == first.total_organization_count

        def override_db():
            yield session

        app.dependency_overrides[get_db] = override_db
        try:
            with TestClient(app) as client:
                summary = client.get("/api/v1/organizations/summary")
                page = client.get(
                    "/api/v1/organizations", params={"search": "优必选", "limit": 10}
                )
        finally:
            app.dependency_overrides.clear()
        assert summary.status_code == 200
        assert summary.json()["total"] == first.total_organization_count
        assert summary.json()["enterprise_count"] >= 1190
        assert summary.json()["university_count"] >= 230
        assert page.status_code == 200
        assert page.json()["total"] >= 1
        assert any("优必选" in item["name"] for item in page.json()["items"])
