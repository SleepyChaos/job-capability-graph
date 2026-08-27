from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.modules.ingestion.service import WorkbookStagingService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将XLSX不可变原始行写入本地导入账本。")
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--storage-key", required=True)
    parser.add_argument("--importer-code", required=True)
    parser.add_argument("--mapping-code", required=True)
    parser.add_argument("--mapping-version", required=True)
    parser.add_argument(
        "--classification",
        choices=["public", "project_internal", "restricted", "personal_sensitive"],
        default="project_internal",
    )
    parser.add_argument(
        "--external-key",
        action="append",
        default=[],
        metavar="SHEET=FIELD",
        help="指定工作表的外部主键字段，可重复使用。",
    )
    parser.add_argument(
        "--sheet",
        action="append",
        default=[],
        help="只暂存指定工作表，可重复使用；省略时暂存全部工作表。",
    )
    return parser.parse_args()


def parse_external_keys(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        sheet, separator, field = value.partition("=")
        if not separator or not sheet or not field:
            raise ValueError(f"无效的 --external-key：{value!r}，应为 SHEET=FIELD")
        result[sheet] = field
    return result


def main() -> None:
    args = parse_args()
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        result = WorkbookStagingService(session).stage(
            args.file,
            storage_object_key=args.storage_key,
            importer_code=args.importer_code,
            mapping_code=args.mapping_code,
            mapping_version=args.mapping_version,
            access_classification=args.classification,
            external_key_fields=parse_external_keys(args.external_key),
            include_sheets=set(args.sheet) if args.sheet else None,
        )
    print(json.dumps(asdict(result), ensure_ascii=False))


if __name__ == "__main__":
    main()
