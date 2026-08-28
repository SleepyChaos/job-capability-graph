"""Re-run matching for profiles from a completed resume experiment."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx

from tools.run_resume_experiment import relevant, summarize, write_outputs


def rematch(api_url: str, source: dict[str, Any]) -> dict[str, Any]:
    row = json.loads(json.dumps(source, ensure_ascii=False))
    if row.get("status") != "completed":
        return row
    with httpx.Client(timeout=httpx.Timeout(240.0, connect=10.0)) as client:
        response = client.post(
            f"{api_url}/talent/profiles/{row['version_code']}/matches",
            params={"limit": 5},
        )
        response.raise_for_status()
        match = response.json()
    role = str(row.get("expected_role") or "")
    top5 = []
    for item in match.get("results") or []:
        detail = item.get("job_detail") or {}
        top5.append(
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
                "role_relevance": (
                    ((item.get("recommendation") or {}).get("retrieval") or {}).get(
                        "role_relevance"
                    )
                ),
                "role_relevance_band": (
                    ((item.get("recommendation") or {}).get("retrieval") or {}).get(
                        "role_relevance_band"
                    )
                ),
            }
        )
    row.update(
        {
            "top5": top5,
            "algorithm_version": match.get("algorithm_version"),
            "candidate_count": match.get("candidate_count"),
            "top1_hit": bool(top5 and top5[0]["relevant_by_title"]),
            "top3_hit": any(item["relevant_by_title"] for item in top5[:3]),
            "top5_relevant_count": sum(item["relevant_by_title"] for item in top5),
            "job_detail_complete_count": sum(item["detail_complete"] for item in top5),
        }
    )
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--api-url", default="http://localhost:8001/api/v1")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    payload = json.loads(args.source.read_text(encoding="utf-8"))
    source_rows = list(payload.get("rows") or [])
    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(rematch, args.api_url, row): row for row in source_rows
        }
        for index, future in enumerate(as_completed(futures), 1):
            row = future.result()
            rows.append(row)
            print(
                json.dumps(
                    {
                        "progress": f"{index}/{len(source_rows)}",
                        "file": Path(str(row.get("file"))).name,
                        "status": row.get("status"),
                        "top3_hit": row.get("top3_hit"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            write_outputs(args.output, rows, summarize(rows))
    print(json.dumps({"summary": summarize(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
