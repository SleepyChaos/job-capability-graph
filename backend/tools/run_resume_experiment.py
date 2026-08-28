"""Run a reproducible resume-upload, dialogue, and matching experiment."""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from app.modules.talent.resume_adapter import ResumeFileError, extract_resume_text

ROLE_TERMS = (
    "嵌入式", "工具链", "财务", "采购", "短视频", "防爆", "工业设计", "机械",
    "结构", "工艺", "立库", "人才发展", "人力资源", "员工关系", "证券", "质量",
    "品质", "材料", "光学", "数采", "数字设计", "信息安全", "销售", "客户",
    "HRIS", "USB", "SoC", "电气", "软件", "算法", "仿真", "测试", "验证",
    "硬件", "电子", "产品", "项目", "供应商", "机器人", "视觉", "运营", "市场",
)


def expected_role(path: Path) -> str:
    value = path.stem
    value = re.sub(r"^简历\s*\d+\s*[：:]\s*", "", value)
    value = re.sub(r"[（(]?J?\w*\d{4,}[）)]?", "", value, flags=re.I)
    value = re.sub(r"简历|标准模板|通用模板|上海", "", value)
    return re.sub(r"[_+\-]+", " ", value).strip(" _-+")


def role_terms(role: str) -> list[str]:
    found = [term for term in ROLE_TERMS if term.casefold() in role.casefold()]
    if found:
        return found
    stem = re.sub(
        r"资深|高级|初级|中级|经理|总监|专家|工程师|设计师|架构师|专员|实习生|方向",
        "",
        role,
    ).strip()
    return [stem] if len(stem) >= 2 else [role]


def relevant(role: str, title: str) -> bool:
    normalized_title = title.casefold().replace(" ", "")
    return any(term.casefold().replace(" ", "") in normalized_title for term in role_terms(role))


def answer_for(question: dict[str, Any], role: str) -> str:
    code = question.get("question_code")
    answers = {
        "target_role": f"目标岗位为{role}，具体工作方向以简历原文中的经历为准。",
        "job_responsibilities": "补充内容以简历中明确写出的个人职责、行动和结果为准。",
        "required_skills": "补充内容以简历中明确写出的实际技能和对应任务为准。",
        "tools_platforms": "补充内容以简历中明确写出的软件、框架、设备和平台为准。",
        "education_major": "学历、学校、专业和毕业时间以简历原文为准。",
        "work_experience": "公司、岗位、起止时间和工作内容以简历原文为准。",
        "application_scenarios": f"优先考虑与{role}直接相关、且简历原文明确出现的应用场景。",
        "generic_capabilities": "通用能力只采用简历原文中有具体行为或结果支持的内容。",
        "representative_project": (
            f"以简历中与{role}最相关的项目为代表，个人职责和结果以简历原文为准。"
        ),
        "work_preference": "偏向工程交付，同时接受与岗位要求相关的跨模块协作。",
        "target_level": "岗位级别以现有经历和岗位要求相匹配为准，可接受合理的相邻方向转型。",
        "target_scenario": f"优先考虑与{role}直接相关的行业场景和产品形态。",
        "development_horizon": "希望在三到六个月内完成岗位衔接。",
        "constraints": "暂不增加简历原文以外的地点或工作条件限制。",
        "additional_evidence": "本轮不新增简历原文以外的项目、论文、竞赛或开源成果。",
    }
    return answers.get(str(code), "本轮回答仅以简历原文中已经提供的事实为准。")


def fetch_job_titles(client: httpx.Client, api_url: str) -> list[str]:
    titles: list[str] = []
    offset = 0
    while True:
        response = client.get(f"{api_url}/jobs", params={"limit": 200, "offset": offset})
        response.raise_for_status()
        payload = response.json()
        items = payload.get("items") or []
        titles.extend(str(item.get("title") or "") for item in items)
        offset += len(items)
        if not items or offset >= int(payload.get("total") or 0):
            return titles


def preflight(path: Path) -> tuple[str, int, str | None]:
    try:
        text, _, _ = extract_resume_text(path.name, path.read_bytes())
        return "ok", len(text), None
    except ResumeFileError as exc:
        return "failed", 0, str(exc)


def process_resume(
    client: httpx.Client,
    api_url: str,
    path: Path,
    all_job_titles: list[str],
) -> dict[str, Any]:
    started = time.monotonic()
    role = expected_role(path)
    status, text_length, preflight_error = preflight(path)
    row: dict[str, Any] = {
        "file": str(path),
        "folder": path.parent.name,
        "expected_role": role,
        "expected_terms": role_terms(role),
        "preflight_status": status,
        "extracted_text_length": text_length,
        "preflight_error": preflight_error,
        "database_coverage_count": sum(relevant(role, title) for title in all_job_titles),
        "questions": [],
        "top5": [],
    }
    if status != "ok":
        row["status"] = "upload_unparseable"
        row["elapsed_seconds"] = round(time.monotonic() - started, 2)
        return row
    try:
        with path.open("rb") as handle:
            response = client.post(
                f"{api_url}/talent/profiles/upload",
                files={
                    "file": (
                        path.name,
                        handle,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                },
            )
        response.raise_for_status()
        profile = response.json()
        row.update(
            {
                "version_code": profile.get("version_code"),
                "extraction_method": (
                    ((profile.get("facts") or {}).get("extraction") or {}).get("method")
                ),
                "skill_count": profile.get("skill_count"),
            }
        )
        for _ in range(2):
            question = profile.get("next_question")
            if not question:
                break
            row["questions"].append(question)
            response = client.post(
                f"{api_url}/talent/profiles/{profile['version_code']}/answers",
                json={"answer_text": answer_for(question, role)},
            )
            response.raise_for_status()
            profile = response.json()
        row["question_count"] = len(row["questions"])
        if not profile.get("can_publish"):
            row["status"] = "insufficient_dialogue"
            row["elapsed_seconds"] = round(time.monotonic() - started, 2)
            return row
        response = client.post(f"{api_url}/talent/profiles/{profile['version_code']}/publish")
        response.raise_for_status()
        response = client.post(
            f"{api_url}/talent/profiles/{profile['version_code']}/matches",
            params={"limit": 5},
        )
        response.raise_for_status()
        match = response.json()
        for item in match.get("results") or []:
            detail = item.get("job_detail") or {}
            row["top5"].append(
                {
                    "rank": item.get("rank_no"),
                    "title": item.get("job_title"),
                    "company": detail.get("company"),
                    "score": item.get("overall_score"),
                    "job_code": detail.get("job_code"),
                    "relevant_by_title": relevant(role, str(item.get("job_title") or "")),
                    "detail_complete": all(
                        detail.get(field)
                        for field in ("job_code", "title_raw", "jd_text", "posting_status")
                    ),
                }
            )
        row.update(
            {
                "status": "completed",
                "algorithm_version": match.get("algorithm_version"),
                "candidate_count": match.get("candidate_count"),
                "top1_hit": bool(row["top5"] and row["top5"][0]["relevant_by_title"]),
                "top3_hit": any(item["relevant_by_title"] for item in row["top5"][:3]),
                "top5_relevant_count": sum(item["relevant_by_title"] for item in row["top5"]),
                "job_detail_complete_count": sum(item["detail_complete"] for item in row["top5"]),
            }
        )
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        row["status"] = "api_failed"
        row["api_error"] = str(exc)
    row["elapsed_seconds"] = round(time.monotonic() - started, 2)
    return row


def process_resume_with_client(
    api_url: str,
    path: Path,
    all_job_titles: list[str],
) -> dict[str, Any]:
    with httpx.Client(timeout=httpx.Timeout(240.0, connect=10.0)) as client:
        return process_resume(client, api_url, path, all_job_titles)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in rows if row.get("status") == "completed"]
    covered = [row for row in completed if row.get("database_coverage_count", 0) > 0]
    question_texts = [
        question.get("question_text")
        for row in completed
        for question in row.get("questions", [])
        if question.get("question_text")
    ]
    counts = Counter(question_texts)
    repeated = sum(count - 1 for count in counts.values() if count > 1)
    top5_total = sum(len(row.get("top5", [])) for row in covered)
    return {
        "resume_count": len(rows),
        "status_counts": dict(Counter(row.get("status") for row in rows)),
        "completed_count": len(completed),
        "database_covered_completed_count": len(covered),
        "question_count": len(question_texts),
        "exact_repeated_question_count": repeated,
        "exact_question_repetition_rate": (
            round(repeated / len(question_texts), 4) if question_texts else None
        ),
        "top1_hit_rate_covered": (
            round(sum(row["top1_hit"] for row in covered) / len(covered), 4)
            if covered
            else None
        ),
        "top3_hit_rate_covered": (
            round(sum(row["top3_hit"] for row in covered) / len(covered), 4)
            if covered
            else None
        ),
        "top5_title_relevance_rate_covered": (
            round(
                sum(row["top5_relevant_count"] for row in covered) / top5_total,
                4,
            )
            if top5_total
            else None
        ),
        "job_detail_completion_rate": round(
            sum(row.get("job_detail_complete_count", 0) for row in completed)
            / max(1, sum(len(row.get("top5", [])) for row in completed)),
            4,
        ),
        "question_code_counts": dict(
            Counter(
                question.get("question_code")
                for row in completed
                for question in row.get("questions", [])
            )
        ),
        "note": "岗位命中为文件名预期岗位与岗位标题的关键词启发式判断，需结合原始结果人工复核。",
    }


def write_outputs(output_dir: Path, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    columns = (
        "file", "folder", "expected_role", "status", "preflight_status",
        "extracted_text_length", "preflight_error", "extraction_method", "skill_count",
        "database_coverage_count", "question_count", "top1_hit", "top3_hit",
        "top5_relevant_count", "job_detail_complete_count", "algorithm_version",
        "candidate_count", "elapsed_seconds", "api_error",
    )
    with (output_dir / "results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--api-url", default="http://localhost:8001/api/v1")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--one-per-folder", action="store_true")
    parser.add_argument("--resume-from", type=Path)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    files = sorted(args.root.rglob("*.docx"))
    if args.one_per_folder:
        selected: dict[Path, Path] = {}
        for path in files:
            selected.setdefault(path.parent, path)
        files = list(selected.values())
    if args.limit:
        files = files[: args.limit]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = args.output or Path("outputs") / f"resume-experiment-{stamp}"
    rows: list[dict[str, Any]] = []
    if args.resume_from:
        previous = json.loads(args.resume_from.read_text(encoding="utf-8"))
        rows = list(previous.get("rows") or [])
    completed_files = {str(row.get("file")) for row in rows}
    pending_files = [path for path in files if str(path) not in completed_files]
    with httpx.Client(timeout=httpx.Timeout(240.0, connect=10.0)) as client:
        job_titles = fetch_job_titles(client, args.api_url)
    if args.workers < 1 or args.workers > 4:
        raise SystemExit("--workers 必须在 1 到 4 之间")
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_resume_with_client,
                args.api_url,
                path,
                job_titles,
            ): path
            for path in pending_files
        }
        for index, future in enumerate(as_completed(futures), len(rows) + 1):
            path = futures[future]
            row = future.result()
            rows.append(row)
            print(
                json.dumps(
                    {
                        "progress": f"{index}/{len(files)}",
                        "file": path.name,
                        "status": row.get("status"),
                        "questions": [q.get("question_code") for q in row.get("questions", [])],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            write_outputs(output, rows, summarize(rows))
    print(json.dumps({"output": str(output), "summary": summarize(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
