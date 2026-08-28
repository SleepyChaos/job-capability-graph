"""Evaluate frozen R-DAEA-PJF experiment exports without calling an LLM."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from app.modules.talent.evaluation import (
    evaluate_active_acquisition,
    evaluate_matching_labels,
    evaluate_resume_entities,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume-gold", type=Path)
    parser.add_argument("--resume-predictions", type=Path)
    parser.add_argument("--matching-gold", type=Path)
    parser.add_argument("--matching-predictions", type=Path)
    parser.add_argument("--acquisition-results", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "evaluation_policy": "frozen_predictions_no_llm_calls",
    }
    if args.resume_gold and args.resume_predictions:
        report["resume_extraction"] = evaluate_resume_entities(
            _read_records(args.resume_gold),
            _read_records(args.resume_predictions),
        )
    if args.matching_gold and args.matching_predictions:
        report["matching"] = evaluate_matching_labels(
            _read_records(args.matching_gold),
            _read_records(args.matching_predictions),
        )
    if args.acquisition_results:
        report["active_acquisition"] = evaluate_active_acquisition(
            _read_records(args.acquisition_results)
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _read_records(path: Path) -> list[dict]:
    if path.suffix.casefold() == ".jsonl":
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, list):
        raise ValueError(f"expected a JSON array or JSONL records: {path}")
    return payload


if __name__ == "__main__":
    main()
