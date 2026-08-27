from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.modules.job.parsing_service import JobParsingService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="结构化解析正式JD并生成聚类特征快照。")
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument("--target-date", type=date.fromisoformat, required=True)
    parser.add_argument("--parser-version", default="jd_structure_rules_v1")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        result = JobParsingService(session).run(
            taxonomy_version_code=args.taxonomy_version,
            target_date=args.target_date,
            parser_version=args.parser_version,
        )
    print(json.dumps(asdict(result), ensure_ascii=False))


if __name__ == "__main__":
    main()
