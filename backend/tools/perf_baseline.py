"""性能基线（计划 E8）：合成数据吞吐与图谱/匹配耗时基线。

用法：
    uv run python tools/perf_baseline.py [--jd-count 3000]

测量项：
    1. SimHash 近重复聚簇吞吐（合成 JD 文本）
    2. 热力图投影耗时（真实演示库）
    3. 全局关联图投影耗时（真实演示库）
    4. 人岗匹配耗时（取任一已确认画像）

报告：data/processed/reports/perf_baseline.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.modules.extraction.near_duplicate import near_duplicate_clusters  # noqa: E402

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = REPOSITORY_ROOT / "data" / "processed" / "reports" / "perf_baseline.json"

TEMPLATE = (
    "负责{tech}模块的开发与优化，参与机器人系统工程联调。"
    "要求熟悉{tech2}，具备项目交付经验，能够独立完成方案设计与验证。"
)
TECH_POOL = [
    "SLAM", "运动规划", "传感器融合", "实时控制", "ROS2", "点云处理",
    "强化学习", "模仿学习", "视觉感知", "力控", "仿真", "嵌入式",
]


def _synthetic_texts(count: int) -> list[str]:
    random.seed(20260812)
    texts = []
    for index in range(count):
        tech, tech2 = random.sample(TECH_POOL, 2)
        texts.append(TEMPLATE.format(tech=tech, tech2=tech2) + f"编号{index}")
    # 注入 5% 近重复转载
    reposts = [texts[i].replace("编号", "转载编号") for i in range(0, count, 20)]
    return texts + reposts


def bench_near_duplicate(count: int) -> dict:
    texts = _synthetic_texts(count)
    items = list(enumerate(texts))
    started = time.perf_counter()
    clusters = near_duplicate_clusters(items)
    elapsed = time.perf_counter() - started
    return {
        "input_documents": len(texts),
        "near_duplicate_clusters": len(clusters),
        "elapsed_seconds": round(elapsed, 3),
        "throughput_docs_per_second": round(len(texts) / elapsed, 1) if elapsed else None,
    }


def bench_graph() -> dict:
    from app.modules.graph.service import heatmap_graph, relation_graph

    result = {}
    with SessionLocal() as db:
        started = time.perf_counter()
        heatmap_graph(db, level_code="L2")
        result["heatmap_seconds"] = round(time.perf_counter() - started, 3)
        started = time.perf_counter()
        relation_graph(db, level_code="L2")
        result["relation_graph_seconds"] = round(time.perf_counter() - started, 3)
    return result


def bench_matching() -> dict:
    from app.modules.talent.models import CandidateProfileVersion
    from app.modules.talent.service import run_matching

    with SessionLocal() as db:
        version = db.scalar(
            select(CandidateProfileVersion)
            .where(CandidateProfileVersion.workflow_status_code == "confirmed")
            .order_by(CandidateProfileVersion.created_at.desc())
        )
        if version is None:
            return {"status": "skipped", "reason": "无已确认画像"}
        started = time.perf_counter()
        match = run_matching(db, version_code=version.version_code, limit=5)
        elapsed = time.perf_counter() - started
        return {
            "profile_version_code": version.version_code,
            "result_count": match["result_count"],
            "elapsed_seconds": round(elapsed, 3),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jd-count", type=int, default=3000)
    args = parser.parse_args()

    report = {
        "near_duplicate": bench_near_duplicate(args.jd_count),
        "graph": bench_graph(),
        "matching": bench_matching(),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n报告已写入：{REPORT_PATH}")


if __name__ == "__main__":
    main()
