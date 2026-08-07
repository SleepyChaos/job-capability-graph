"""提取准确率评测：对照真值标注计算 precision / recall / F1。

真值文件：data/sample_ground_truth.json（{job_id: [技术词...]}）
对照口径：统一库 job_skills JOIN skills 的 skill_term。
"""
from __future__ import annotations

import argparse
import json

from . import config, db


def evaluate(truth_path: str | None = None) -> dict:
    truth_path = truth_path or str(config.DATA_DIR / "sample_ground_truth.json")
    with open(truth_path, encoding="utf-8") as f:
        truth: dict[str, list[str]] = json.load(f)

    conn = db.connect()
    rows = conn.execute(
        """
        SELECT js.job_id, s.skill_term
        FROM job_skills js JOIN skills s ON js.skill_id = s.skill_id
        """
    ).fetchall()
    conn.close()

    predicted: dict[str, set[str]] = {}
    for r in rows:
        predicted.setdefault(r["job_id"], set()).add(r["skill_term"])

    tp = fp = fn = 0
    for job_id, terms in truth.items():
        gold = {db_norm(t) for t in terms}
        pred = {db_norm(t) for t in predicted.get(job_id, set())}
        tp += len(gold & pred)
        fp += len(pred - gold)
        fn += len(gold - pred)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    result = {
        "jobs": len(truth), "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
    }
    print("=== 提取准确率评测 ===")
    print(f"岗位数: {result['jobs']}  TP={tp} FP={fp} FN={fn}")
    print(f"Precision: {precision:.2%}  Recall: {recall:.2%}  F1: {f1:.2%}")
    if precision >= 0.9 and recall >= 0.9:
        print("✅ 达到赛题要求（≥90%）")
    else:
        print("⚠️ 未达 90%，检查漏提/误提词条")
    return result


def db_norm(term: str) -> str:
    """与 extract.normalize_text 一致的口径。"""
    from .extract import normalize_text
    return normalize_text(term)


def main() -> None:
    parser = argparse.ArgumentParser(description="提取准确率评测")
    parser.add_argument("--truth", default=None, help="真值 JSON 文件路径")
    args = parser.parse_args()
    evaluate(args.truth)


if __name__ == "__main__":
    main()
