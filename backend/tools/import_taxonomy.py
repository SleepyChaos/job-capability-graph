from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date

from sqlalchemy import select

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.modules.ingestion.models import FileImportRun
from app.modules.taxonomy.service import TaxonomyImportService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将已暂存技术词工作簿发布到技术主数据表。")
    parser.add_argument("--mapping-code", required=True)
    parser.add_argument("--version-code", required=True)
    parser.add_argument("--version-name", required=True)
    parser.add_argument("--effective-date", type=date.fromisoformat, required=True)
    parser.add_argument("--domain-version", required=True)
    parser.add_argument("--change-summary")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        import_run = session.scalar(
            select(FileImportRun)
            .where(FileImportRun.mapping_code == args.mapping_code)
            .order_by(FileImportRun.created_at.desc())
            .limit(1)
        )
        if import_run is None:
            raise SystemExit(f"找不到映射{args.mapping_code}对应的文件导入运行")
        result = TaxonomyImportService(session).publish(
            file_import_run_id=import_run.file_import_run_id,
            version_code=args.version_code,
            version_name=args.version_name,
            effective_date=args.effective_date,
            domain_version=args.domain_version,
            change_summary=args.change_summary,
        )
    print(json.dumps(asdict(result), ensure_ascii=False))


if __name__ == "__main__":
    main()
