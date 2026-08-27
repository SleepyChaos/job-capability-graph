from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import subprocess
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.job.models import (
    JobParseResult,
    JobParseRun,
    JobPosting,
    JobRequirement,
    JobResponsibility,
    JobScenario,
)
from app.modules.taxonomy.models import TechnologyNode

ROOT = Path(__file__).resolve().parents[2]


def normalize(value: str | None) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (value or "").casefold())


def bigrams(value: str) -> set[str]:
    return {value[index : index + 2] for index in range(max(0, len(value) - 1))}


def similarity(left: str | None, right: str | None) -> float:
    a, b = normalize(left), normalize(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if min(len(a), len(b)) >= 2 and (a in b or b in a):
        return max(0.7, min(len(a), len(b)) / max(len(a), len(b)))
    ga, gb = bigrams(a), bigrams(b)
    return 2 * len(ga & gb) / (len(ga) + len(gb)) if ga and gb else 0.0


def match_items(predicted: list[dict], gold: list[dict], threshold: float) -> dict:
    candidates = []
    for p_index, pred in enumerate(predicted):
        for g_index, target in enumerate(gold):
            score = similarity(pred["value"], target["normalized_value"])
            candidates.append((score, p_index, g_index))
    used_pred: set[int] = set()
    used_gold: set[int] = set()
    matches = []
    for score, p_index, g_index in sorted(candidates, reverse=True):
        if score < threshold or p_index in used_pred or g_index in used_gold:
            continue
        used_pred.add(p_index)
        used_gold.add(g_index)
        matches.append((p_index, g_index, score))
    tp = len(matches)
    fp = len(predicted) - tp
    fn = len(gold) - tp
    precision = tp / (tp + fp) if tp + fp else (1.0 if not gold else 0.0)
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    evidence_hits = 0
    for p_index, g_index, _score in matches:
        if similarity(predicted[p_index].get("evidence"), gold[g_index].get("evidence_text")) >= 0.45:
            evidence_hits += 1
    evidence_rate = evidence_hits / len(matches) if matches else (1.0 if not gold and not predicted else 0.0)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "evidence_hits": evidence_hits,
        "evidence_rate": evidence_rate,
    }


def aggregate(rows: list[dict], field: str) -> dict:
    tp = sum(row[field]["tp"] for row in rows)
    fp = sum(row[field]["fp"] for row in rows)
    fn = sum(row[field]["fn"] for row in rows)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "macro_f1": round(sum(row[field]["f1"] for row in rows) / len(rows), 4),
        "evidence_accuracy": round(
            sum(row[field]["evidence_hits"] for row in rows)
            / max(1, sum(row[field]["tp"] for row in rows)),
            4,
        ),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def bootstrap_ci(values: list[float], iterations: int = 2000) -> list[float]:
    rng = random.Random(20260821)
    means = []
    for _ in range(iterations):
        means.append(sum(rng.choice(values) for _ in values) / len(values))
    means.sort()
    return [round(means[int(iterations * 0.025)], 4), round(means[int(iterations * 0.975)], 4)]


def git_revision() -> dict:
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
        return {"commit": head, "dirty": dirty}
    except Exception as exc:  # pragma: no cover - provenance fallback
        return {"commit": "unavailable", "dirty": None, "error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser(description="JD 120条冻结集粗版基线评测。")
    parser.add_argument(
        "--gold",
        type=Path,
        default=ROOT / "data/evaluation/jd_parsing/jd_parsing_test_set_v1_1.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--failure-csv", type=Path, required=True)
    parser.add_argument("--match-threshold", type=float, default=0.45)
    args = parser.parse_args()
    started = datetime.now()
    gold = json.loads(args.gold.read_text(encoding="utf-8"))
    run_code = gold["parse_run_code"]
    results = []
    missing = []
    with SessionLocal() as db:
        run = db.scalar(select(JobParseRun).where(JobParseRun.run_code == run_code))
        if run is None:
            raise SystemExit(f"找不到解析批次 {run_code}")
        node_codes = {
            node.technology_node_id: node.technology_code
            for node in db.scalars(select(TechnologyNode))
        }
        for sample in gold["samples"]:
            job = db.scalar(select(JobPosting).where(JobPosting.job_code == sample["job_code"]))
            if job is None:
                missing.append(sample["sample_id"])
                continue
            parse_result = db.get(JobParseResult, (run.job_parse_run_id, job.job_posting_id))
            if parse_result is None:
                missing.append(sample["sample_id"])
                continue
            responsibilities = [
                {"value": row.normalized_task_text or row.raw_text, "evidence": row.raw_text}
                for row in db.scalars(
                    select(JobResponsibility)
                    .where(
                        JobResponsibility.job_parse_run_id == run.job_parse_run_id,
                        JobResponsibility.job_posting_id == job.job_posting_id,
                    )
                    .order_by(JobResponsibility.responsibility_no)
                )
            ]
            requirements = list(
                db.scalars(
                    select(JobRequirement)
                    .where(JobRequirement.job_posting_id == job.job_posting_id)
                    .order_by(JobRequirement.requirement_no)
                )
            )
            required = [
                {"value": row.raw_term or row.raw_text, "evidence": row.raw_text}
                for row in requirements
                if row.requirement_type_code == "required"
            ]
            bonus = [
                {"value": row.raw_term or row.raw_text, "evidence": row.raw_text}
                for row in requirements
                if row.requirement_type_code == "bonus"
            ]
            scenarios = [
                {"value": row.normalized_scenario or row.scenario_text, "evidence": row.scenario_text}
                for row in db.scalars(
                    select(JobScenario)
                    .where(JobScenario.job_posting_id == job.job_posting_id)
                    .order_by(JobScenario.scenario_no)
                )
            ]
            gold_annotation = sample["annotation"]
            field_results = {
                "responsibilities": match_items(responsibilities, gold_annotation["responsibilities"], args.match_threshold),
                "required_skills": match_items(required, gold_annotation["required_skills"], args.match_threshold),
                "bonus_skills": match_items(bonus, gold_annotation["bonus_skills"], args.match_threshold),
                "application_scenarios": match_items(scenarios, gold_annotation["application_scenarios"], args.match_threshold),
            }
            gold_title = gold_annotation["job_title"][0]["normalized_value"] if gold_annotation["job_title"] else ""
            title_exact = normalize(job.job_title_normalized) == normalize(gold_title)
            title_relaxed = similarity(job.job_title_normalized, gold_title) >= 0.7
            predicted_codes = {
                node_codes[row.technology_node_id]
                for row in requirements
                if row.technology_node_id in node_codes
            }
            gold_codes = set(gold_annotation.get("technology_codes", [])) - {"unmapped"}
            evaluable_codes = bool(gold_codes)
            sample_score = (
                float(title_relaxed)
                + sum(field_results[name]["f1"] for name in field_results)
            ) / 5
            results.append(
                {
                    "sample_id": sample["sample_id"],
                    "job_code": sample["job_code"],
                    "domain": sample["primary_domain"],
                    "title_gold": gold_title,
                    "title_predicted": job.job_title_normalized,
                    "title_exact": title_exact,
                    "title_relaxed": title_relaxed,
                    "parse_status": parse_result.parse_status_code,
                    "review_required": parse_result.review_required,
                    "parse_quality_score": float(parse_result.parse_quality_score),
                    "predicted_technology_codes": sorted(predicted_codes),
                    "gold_technology_codes": sorted(gold_codes),
                    "technology_code_evaluable": evaluable_codes,
                    **field_results,
                    "sample_macro_score": sample_score,
                }
            )
    fields = ["responsibilities", "required_skills", "bonus_skills", "application_scenarios"]
    metrics = {field: aggregate(results, field) for field in fields}
    title_exact_rate = sum(row["title_exact"] for row in results) / len(results)
    title_relaxed_rate = sum(row["title_relaxed"] for row in results) / len(results)
    overall_values = [row["sample_macro_score"] for row in results]
    evaluable_code_rows = [row for row in results if row["technology_code_evaluable"]]
    finished = datetime.now()
    report = {
        "status": "preliminary_baseline_not_formal_acceptance",
        "dataset_id": gold["dataset_id"],
        "dataset_status": gold["status"],
        "annotation_limitation": "single annotator, two blind passes; no independent second annotator or adjudicator",
        "sample_count": len(results),
        "missing_count": len(missing),
        "missing_sample_ids": missing,
        "parse_run_code": run_code,
        "parse_run_completed_at": run.completed_at.isoformat() if run and run.completed_at else None,
        "evaluation_started_at": started.isoformat(timespec="seconds"),
        "evaluation_finished_at": finished.isoformat(timespec="seconds"),
        "evaluation_seconds": round((finished - started).total_seconds(), 3),
        "code_version": git_revision(),
        "matching_rule": {"normalization": "lowercase + remove punctuation/whitespace", "relaxed_threshold": args.match_threshold, "method": "greedy character-bigram/substring matching"},
        "title_exact_match": round(title_exact_rate, 4),
        "title_relaxed_match": round(title_relaxed_rate, 4),
        "fields": metrics,
        "preliminary_overall_macro": round(sum(overall_values) / len(overall_values), 4),
        "preliminary_overall_95ci": bootstrap_ci(overall_values),
        "technology_code_accuracy": None,
        "technology_code_evaluable_samples": len(evaluable_code_rows),
        "technology_code_note": "冻结集技术编码为unmapped，当前不可评估编码准确率。",
        "education_major_experience_metrics": None,
        "missing_metrics_note": "学历、专业、工作年限未在v1.1人工真值中独立标注。",
        "threshold_90_conclusion": "not_claimable_from_preliminary_baseline",
        "failure_count_below_0_9": sum(value < 0.9 for value in overall_values),
        "samples": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.failure_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.failure_csv.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["sample_id", "job_code", "domain", "title_gold", "title_predicted", "title_exact", "overall", *[f"{field}_f1" for field in fields]])
        for row in sorted(results, key=lambda item: item["sample_macro_score"]):
            writer.writerow([row["sample_id"], row["job_code"], row["domain"], row["title_gold"], row["title_predicted"], row["title_exact"], round(row["sample_macro_score"], 4), *[round(row[field]["f1"], 4) for field in fields]])
    print(json.dumps({key: report[key] for key in report if key != "samples"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
