from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.ingestion.models import SpreadsheetRow
from app.modules.ingestion.service import WorkbookStagingService
from app.modules.taxonomy.service import TaxonomyImportError, TaxonomyImportService


def test_real_taxonomy_import_and_query_api() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    workbook_path = (
        repository_root / "data" / "source" / "20260810" / "core" / "技术词主数据_20260727.xlsx"
    )
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        staged = WorkbookStagingService(session).stage(
            workbook_path,
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
        source_row = session.scalar(
            select(SpreadsheetRow)
            .where(SpreadsheetRow.sheet_name == "L4技术词")
            .order_by(SpreadsheetRow.source_row_number)
            .limit(1)
        )
        assert source_row is not None
        original_payload = dict(source_row.row_payload_json)
        invalid_payload = dict(original_payload)
        invalid_payload["挂载L3编码"] = "MISSING-L3"
        source_row.row_payload_json = invalid_payload
        session.flush()
        with pytest.raises(TaxonomyImportError, match="引用不存在的L3"):
            TaxonomyImportService(session).publish(
                file_import_run_id=staged.file_import_run_id,
                version_code="invalid-test",
                version_name="无效测试版本",
                effective_date=date(2026, 7, 27),
                domain_version="invalid-test",
            )
        source_row.row_payload_json = original_payload
        session.flush()

        result = TaxonomyImportService(session).publish(
            file_import_run_id=staged.file_import_run_id,
            version_code="v1.1-test",
            version_name="真实技术主数据测试版本",
            effective_date=date(2026, 7, 27),
            domain_version="v1.1-test",
        )
        assert result.domain_count == 7
        assert result.l1_count == 7
        assert result.l2_count == 43
        assert result.l3_count == 229
        assert result.l4_count == 1872
        assert result.alias_count == 1872
        assert result.domain_relation_count == 2151

        def override_db():
            yield session

        app.dependency_overrides[get_db] = override_db
        try:
            with TestClient(app) as client:
                versions = client.get("/api/v1/taxonomy/versions")
                domains = client.get("/api/v1/taxonomy/domains")
                nodes = client.get(
                    "/api/v1/taxonomy/nodes",
                    params={"level": "L3", "domain_code": "T1", "limit": 10},
                )
        finally:
            app.dependency_overrides.clear()

        assert versions.status_code == 200
        assert versions.json()[0]["node_count"] == 2151
        assert domains.status_code == 200
        assert len(domains.json()) == 7
        assert sum(domain["node_count"] for domain in domains.json()) == 2151
        assert nodes.status_code == 200
        assert nodes.json()["total"] > 0
        assert len(nodes.json()["items"]) == 10
        assert all(node["level"] == "L3" for node in nodes.json()["items"])
        assert all(node["domain_code"] == "T1" for node in nodes.json()["items"])
