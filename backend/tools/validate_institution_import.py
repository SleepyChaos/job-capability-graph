from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.modules.ingestion.models import FileImportRowResult
from app.modules.ingestion.service import WorkbookStagingService
from app.modules.job.institution_import import InstitutionImportService
from app.modules.job.models import Organization


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="在隔离内存库验证机构导入。")
    parser.add_argument("--file", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        stage = WorkbookStagingService(session).stage(
            args.file,
            storage_object_key=str(args.file),
            importer_code="institution_xlsx_validation_v1",
            mapping_code="institution_validation_v1",
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
        type_counts = dict(
            session.execute(
                select(Organization.organization_type_code, func.count()).group_by(
                    Organization.organization_type_code
                )
            ).all()
        )
        row_results = session.scalar(
            select(func.count()).select_from(FileImportRowResult)
        ) or 0
        checks = {
            "source_rows_are_complete": first.source_row_count == 1598,
            "all_rows_processed": first.created_count + first.merged_count == 1598,
            "no_failed_rows": first.failed_count == 0,
            "second_run_is_idempotent": second.already_published,
            "row_results_are_complete": row_results == 1598,
            "organization_types_present": all(
                type_counts.get(code, 0) > 0
                for code in (
                    "enterprise",
                    "university",
                    "research_institute",
                    "government_public",
                )
            ),
        }
        payload = {
            "passed": all(checks.values()),
            "checks": checks,
            "first": asdict(first),
            "second": asdict(second),
            "type_counts": type_counts,
        }
        print(json.dumps(payload, ensure_ascii=False))
        if not payload["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
