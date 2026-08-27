from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.modules.ingestion.models import FileImportRun, RawFileAsset, SpreadsheetRow
from app.modules.ingestion.service import WorkbookStagingService


def test_stage_workbook_is_idempotent(tmp_path: Path) -> None:
    workbook_path = tmp_path / "taxonomy.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "L3技术点"
    sheet.append(["L3编码", "L3标准名"])
    sheet.append(["T1-L3-001", "视觉感知"])
    sheet.append(["T1-L3-002", "触觉感知"])
    workbook.save(workbook_path)

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        service = WorkbookStagingService(session)
        first = service.stage(
            workbook_path,
            storage_object_key="source/taxonomy.xlsx",
            importer_code="taxonomy_importer",
            mapping_code="taxonomy_v1",
            mapping_version="1.0.0",
            access_classification="project_internal",
            external_key_fields={"L3技术点": "L3编码"},
        )
        second = service.stage(
            workbook_path,
            storage_object_key="source/taxonomy.xlsx",
            importer_code="taxonomy_importer",
            mapping_code="taxonomy_v1",
            mapping_version="1.0.0",
            access_classification="project_internal",
            external_key_fields={"L3技术点": "L3编码"},
        )

        assert first.file_asset_id == second.file_asset_id
        assert first.file_import_run_id == second.file_import_run_id
        assert first.staged_row_count == 2
        assert second.staged_row_count == 0
        assert second.skipped_existing_row_count == 2
        assert session.scalar(select(func.count()).select_from(RawFileAsset)) == 1
        assert session.scalar(select(func.count()).select_from(FileImportRun)) == 1
        assert session.scalar(select(func.count()).select_from(SpreadsheetRow)) == 2
        persisted_run = session.scalar(select(FileImportRun))
        assert persisted_run is not None
        assert persisted_run.success_row_count == 2
        assert persisted_run.skipped_row_count == 0
        external_keys = session.scalars(
            select(SpreadsheetRow.external_record_key).order_by(SpreadsheetRow.source_row_number)
        ).all()
        assert external_keys == ["T1-L3-001", "T1-L3-002"]
