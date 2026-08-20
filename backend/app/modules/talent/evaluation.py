"""Offline, reproducible metrics for resume, matching, and acquisition experiments."""

from __future__ import annotations

import re
from collections import Counter

RESUME_ENTITY_TYPES = ("name", "education", "experience", "project", "skill")
MATCH_LABELS = ("match", "partial_match", "nonmatch")


def evaluate_resume_entities(gold_records: list[dict], predictions: list[dict]) -> dict:
    predicted_by_id = {str(item["sample_id"]): item for item in predictions}
    totals = Counter()
    per_type: dict[str, Counter] = {kind: Counter() for kind in RESUME_ENTITY_TYPES}
    sample_results = []
    for gold in gold_records:
        sample_id = str(gold["sample_id"])
        predicted = predicted_by_id.get(sample_id, {"entities": []})
        gold_entities = _entity_set(gold.get("entities", []))
        predicted_entities = _entity_set(predicted.get("entities", []))
        sample_tp = sample_fp = sample_fn = 0
        for kind in RESUME_ENTITY_TYPES:
            gold_values = {value for entity_type, value in gold_entities if entity_type == kind}
            predicted_values = {
                value for entity_type, value in predicted_entities if entity_type == kind
            }
            tp = len(gold_values & predicted_values)
            fp = len(predicted_values - gold_values)
            fn = len(gold_values - predicted_values)
            per_type[kind].update(tp=tp, fp=fp, fn=fn)
            totals.update(tp=tp, fp=fp, fn=fn)
            sample_tp += tp
            sample_fp += fp
            sample_fn += fn
        source_text = str(gold.get("source_text", ""))
        quoted = [
            str(item.get("evidence_quote", ""))
            for item in predicted.get("entities", [])
            if item.get("evidence_quote")
        ]
        valid_quotes = sum(1 for quote in quoted if quote in source_text)
        sample_results.append(
            {
                "sample_id": sample_id,
                **_prf(sample_tp, sample_fp, sample_fn),
                "evidence_quote_validity": valid_quotes / len(quoted) if quoted else None,
            }
        )
    micro = _prf(totals["tp"], totals["fp"], totals["fn"])
    by_type = {
        kind: _prf(counts["tp"], counts["fp"], counts["fn"])
        for kind, counts in per_type.items()
    }
    macro_f1 = sum(item["f1"] for item in by_type.values()) / len(by_type)
    quote_rates = [
        item["evidence_quote_validity"]
        for item in sample_results
        if item["evidence_quote_validity"] is not None
    ]
    return {
        "sample_count": len(gold_records),
        "micro": micro,
        "macro_f1": round(macro_f1, 6),
        "by_entity_type": by_type,
        "evidence_quote_validity": (
            round(sum(quote_rates) / len(quote_rates), 6) if quote_rates else None
        ),
        "target": {"metric": "micro_f1", "threshold": 0.90, "passed": micro["f1"] >= 0.90},
        "samples": sample_results,
    }


def evaluate_matching_labels(gold_records: list[dict], predictions: list[dict]) -> dict:
    predicted_by_id = {str(item["pair_id"]): str(item["label"]) for item in predictions}
    matrix = {gold: {predicted: 0 for predicted in MATCH_LABELS} for gold in MATCH_LABELS}
    missing_predictions = []
    for item in gold_records:
        pair_id = str(item["pair_id"])
        gold = str(item["label"])
        if gold not in MATCH_LABELS:
            raise ValueError(f"unsupported gold matching label: {gold}")
        predicted = predicted_by_id.get(pair_id)
        if predicted not in MATCH_LABELS:
            missing_predictions.append(pair_id)
            continue
        matrix[gold][predicted] += 1
    per_class = {}
    for label in MATCH_LABELS:
        tp = matrix[label][label]
        fp = sum(matrix[other][label] for other in MATCH_LABELS if other != label)
        fn = sum(matrix[label][other] for other in MATCH_LABELS if other != label)
        per_class[label] = _prf(tp, fp, fn)
    scored_count = sum(sum(row.values()) for row in matrix.values())
    correct = sum(matrix[label][label] for label in MATCH_LABELS)
    accuracy = correct / scored_count if scored_count else 0.0
    macro_f1 = sum(item["f1"] for item in per_class.values()) / len(per_class)
    return {
        "gold_count": len(gold_records),
        "scored_count": scored_count,
        "missing_prediction_count": len(missing_predictions),
        "missing_pair_ids": missing_predictions,
        "accuracy": round(accuracy, 6),
        "macro_f1": round(macro_f1, 6),
        "per_class": per_class,
        "confusion_matrix": {
            "labels": list(MATCH_LABELS),
            "rows_gold_columns_predicted": [
                [matrix[gold][predicted] for predicted in MATCH_LABELS]
                for gold in MATCH_LABELS
            ],
        },
        "target": {"metric": "accuracy", "threshold": 0.90, "passed": accuracy >= 0.90},
    }


def evaluate_active_acquisition(records: list[dict]) -> dict:
    if not records:
        return {"sample_count": 0, "status": "pending"}
    baseline_correct = final_correct = 0
    resolved = unsafe = privacy_violations = verification_violations = 0
    widths = []
    question_counts = []
    for item in records:
        gold = item.get("gold_label")
        baseline_correct += item.get("baseline_prediction") == gold
        final_correct += item.get("final_prediction") == gold
        resolved += item.get("final_status") in {"safe_match", "safe_nonmatch"}
        unsafe += (
            item.get("final_status") in {"safe_match", "safe_nonmatch"}
            and item.get("final_prediction") != gold
        )
        privacy_violations += int(bool(item.get("privacy_violation", False)))
        verification_violations += int(bool(item.get("self_claim_promoted_to_verified", False)))
        initial_width = float(item.get("initial_width", 0.0))
        final_width = float(item.get("final_width", initial_width))
        widths.append(initial_width - final_width)
        question_counts.append(int(item.get("question_count", 0)))
    count = len(records)
    return {
        "sample_count": count,
        "baseline_accuracy": round(baseline_correct / count, 6),
        "final_accuracy": round(final_correct / count, 6),
        "accuracy_gain": round((final_correct - baseline_correct) / count, 6),
        "safe_resolution_rate": round(resolved / count, 6),
        "unsafe_decision_rate": round(unsafe / count, 6),
        "mean_interval_shrink": round(sum(widths) / count, 6),
        "mean_question_count": round(sum(question_counts) / count, 6),
        "privacy_violation_count": privacy_violations,
        "self_claim_verification_violation_count": verification_violations,
    }


def _entity_set(entities: list[dict]) -> set[tuple[str, str]]:
    values = set()
    for item in entities:
        kind = str(item.get("type", "")).strip()
        value = _normalize_entity(str(item.get("value", "")))
        if kind in RESUME_ENTITY_TYPES and value:
            values.add((kind, value))
    return values


def _normalize_entity(value: str) -> str:
    return re.sub(r"[\s·•,，。;；:：()（）_\-/]+", "", value.casefold())


def _prf(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }
