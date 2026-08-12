from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from decimal import Decimal

from app.db.session import SessionLocal
from app.modules.job.llm_reassessment_service import (
    LlmTechnologyReassessmentService,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="用配置的 DeepSeek/OpenAI 兼容模型闭集复核待审核技术命中。"
    )
    parser.add_argument("--parse-run-code", required=True)
    parser.add_argument("--batch-size", type=int, default=12)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--apply-threshold", type=Decimal, default=Decimal("0.85"))
    parser.add_argument("--max-context-chars", type=int, default=1200)
    parser.add_argument(
        "--no-apply",
        action="store_true",
        help="仅保存模型审计结果，不改原始 assessment 和聚类特征。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with SessionLocal() as session:
        result = LlmTechnologyReassessmentService(session).run(
            parse_run_code=args.parse_run_code,
            batch_size=args.batch_size,
            limit=args.limit,
            apply_threshold=args.apply_threshold,
            apply_changes=not args.no_apply,
            max_context_chars=args.max_context_chars,
        )
    print(json.dumps(asdict(result), ensure_ascii=False))


if __name__ == "__main__":
    main()
