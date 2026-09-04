from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from sqlalchemy import select

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.modules.ingestion.models import FileImportRun
from app.modules.job.institution_import import InstitutionImportService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将已暂存机构库发布为机构主数据。")
    parser.add_argument("--mapping-code", required=True)
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
        result = InstitutionImportService(session).publish(
            file_import_run_id=import_run.file_import_run_id
        )
    print(json.dumps(asdict(result), ensure_ascii=False))


if __name__ == "__main__":
    main()
