from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime

from sqlalchemy import select

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.modules.ingestion.models import FileImportRun
from app.modules.job.service import JobImportService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将已暂存岗位工作簿发布为正式JD。")
    parser.add_argument("--mapping-code", required=True)
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument("--received-at", type=datetime.fromisoformat, required=True)
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
        result = JobImportService(session).publish(
            file_import_run_id=import_run.file_import_run_id,
            taxonomy_version_code=args.taxonomy_version,
            received_at=args.received_at,
        )
    print(json.dumps(asdict(result), ensure_ascii=False))


if __name__ == "__main__":
    main()
