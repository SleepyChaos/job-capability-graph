from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def metric(rows: list[tuple[float, str]], threshold: float) -> dict[str, float | int]:
    tp = fp = fn = tn = 0
    for score, label in rows:
        predicted_error = score < threshold
        actual_error = label == "incorrect"
        if predicted_error and actual_error:
            tp += 1
        elif predicted_error:
            fp += 1
        elif actual_error:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "threshold": round(threshold, 4), "precision": round(precision, 4),
        "recall": round(recall, 4), "f1": round(f1, 4),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "review_count": tp + fp, "review_rate": round((tp + fp) / len(rows), 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Layer C 50-row pilot calibration; not formal acceptance.")
    parser.add_argument("--labels-json", type=Path, required=True)
    parser.add_argument("--candidates-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--joined-csv", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.labels_json.read_text(encoding="utf-8-sig"))
    labels = {row["sample_id"]: row for row in payload["rows"]}
    joined: list[dict[str, str]] = []
    with args.candidates_csv.open(encoding="utf-8-sig", newline="") as stream:
        for source in csv.DictReader(stream):
            item = labels.get(source["sample_id"])
            if item:
                joined.append({**source, "label": item["label"], "evidence_checked": "true",
                               "annotator": item["annotator"], "note": item["note"]})

    args.joined_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.joined_csv.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(joined[0]))
        writer.writeheader(); writer.writerows(joined)

    counts = {name: sum(row["label"] == name for row in joined)
              for name in ("correct", "incorrect", "insufficient_evidence")}
    usable = [(float(row["plausibility_score"]), row["label"])
              for row in joined if row["label"] in {"correct", "incorrect"}]
    candidates = [metric(usable, i / 1000) for i in range(1, 1000)]
    recall_90 = [item for item in candidates if item["recall"] >= 0.9]
    if recall_90:
        best = max(recall_90, key=lambda x: (x["precision"], x["f1"], -x["review_rate"], -x["threshold"]))
        selection_rule = "错误三元组Recall>=90%，再选Precision最高；并列选F1高、审核率低、阈值低"
    else:
        best = max(candidates, key=lambda x: (x["recall"], x["precision"], x["f1"]))
        selection_rule = "未发现Recall>=90%的候选，退化为Recall优先"
    result = {
        "status": "pilot_single_pass_50_not_formal",
        "completed_rows": len(joined), "usable_rows": len(usable), "label_counts": counts,
        "selection_rule": selection_rule, "pilot_best": best,
        "current_ui_threshold": 0.35,
        "current_ui_threshold_metrics": metric(usable, 0.35),
        "limitations": [
            "仅第一遍单人标注的前50条，尚无第二位独立标注员和第三人仲裁",
            "错误样本仅3条，估计不稳定",
            "尚未划分100条校准集和50条保留测试集",
            "本结果不得写成正式阈值或最终幻觉防控指标",
        ],
        "next_gate": "完成剩余100条、第二遍盲审/仲裁后，按100/50分层划分并只在50条保留集验证一次",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
