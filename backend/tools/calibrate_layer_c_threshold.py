from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def metrics(rows: list[tuple[float, str]], threshold: float) -> dict:
    tp = fp = fn = tn = 0
    for score, label in rows:
        predicted_incorrect = score < threshold
        actual_incorrect = label == "incorrect"
        if predicted_incorrect and actual_incorrect: tp += 1
        elif predicted_incorrect: fp += 1
        elif actual_incorrect: fn += 1
        else: tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"threshold": threshold, "precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    valid = []; insufficient = 0; pending = 0
    with args.input.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            label = row["label"].strip()
            if label == "insufficient_evidence": insufficient += 1
            elif label in {"correct", "incorrect"}: valid.append((float(row["plausibility_score"]), label))
            else: pending += 1
    if pending or not valid:
        result = {"status": "pending_human_adjudication", "labeled": len(valid), "pending": pending, "insufficient_evidence": insufficient}
    else:
        candidates = [metrics(valid, value / 100) for value in range(1, 100)]
        best = max(candidates, key=lambda item: (item["f1"], item["precision"], -item["threshold"]))
        result = {"status": "calibrated_on_adjudicated_set", "sample_count": len(valid), "insufficient_evidence": insufficient, "best": best, "warning": "该阈值仍需独立留出集验证"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
