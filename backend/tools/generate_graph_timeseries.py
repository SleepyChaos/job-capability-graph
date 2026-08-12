"""生成 45 天图谱时序金标准夹具（测试数据集设计方案 §10）。

用法：
    uv run python tools/generate_graph_timeseries.py

输出：data/test/graph_timeseries/graph_timeseries_v1.csv
内容：确定性合成（seed 固定），覆盖 T1–T7 与窗口边界日期，
用于验证热力图 45 天窗口、第 45 天包含/第 46 天排除、去重口径。
"""

from __future__ import annotations

import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.modules.taxonomy.models import (  # noqa: E402
    TechnologyDomain,
    TechnologyNode,
    TechnologyNodeDomain,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPOSITORY_ROOT / "data" / "test" / "graph_timeseries" / "graph_timeseries_v1.csv"
END_DATE = date(2026, 8, 10)
DAYS = 45


def main() -> None:
    random.seed(20260810)
    with SessionLocal() as db:
        domains = [
            code
            for (code,) in db.execute(
                select(TechnologyDomain.domain_code).order_by(TechnologyDomain.sort_order)
            )
        ][:7]
        nodes = list(
            db.scalars(
                select(TechnologyNode)
                .where(TechnologyNode.level_code == "L2")
                .order_by(TechnologyNode.technology_code)
                .limit(200)
            )
        )
        domain_rows = db.execute(
            select(TechnologyNodeDomain.technology_node_id, TechnologyDomain.domain_code)
            .join(
                TechnologyDomain,
                TechnologyDomain.technology_domain_id
                == TechnologyNodeDomain.technology_domain_id,
            )
            .where(
                TechnologyNodeDomain.technology_node_id.in_(
                    [node.technology_node_id for node in nodes] or [-1]
                )
            )
        ).all()
    domain_by_node = {}
    for node_id, domain_code in domain_rows:
        domain_by_node.setdefault(node_id, domain_code)
    tech_rows = [
        (node.technology_code, domain_by_node.get(node.technology_node_id, "T7"))
        for node in nodes
    ]

    # 若联表取不到（模型差异），退化为按域均匀分配合成编码
    if not tech_rows:
        tech_rows = [
            (f"{domain}.99.{index:02d}", domain)
            for domain in domains
            for index in range(1, 6)
        ]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    dates = [END_DATE - timedelta(days=offset) for offset in range(DAYS - 1, -1, -1)]
    # 窗口外各放 1 行，用于验证"第 46 天排除"
    for outside_date in (END_DATE - timedelta(days=DAYS), END_DATE + timedelta(days=1)):
        term_code, domain = tech_rows[0]
        rows.append(
            {
                "event_date": outside_date.isoformat(),
                "term_id": term_code,
                "t_domain": domain,
                "level": "L2",
                "job_cluster_id": "cluster_boundary_check",
                "source_material_id": "material_out_of_window",
                "trigger_count": 1,
                "is_verified": "true",
            }
        )
    for day_index, metric_date in enumerate(dates):
        # 前 2 天为主要观测日（贴合当前数据边界），其余稀疏
        active_terms = random.sample(tech_rows, 14 if day_index < 2 else 4)
        for term_code, domain in active_terms:
            rows.append(
                {
                    "event_date": metric_date.isoformat(),
                    "term_id": term_code,
                    "t_domain": domain,
                    "level": "L2",
                    "job_cluster_id": f"cluster_{domain.lower()}_syn",
                    "source_material_id": f"material_{day_index:02d}_{term_code}",
                    "trigger_count": random.randint(1, 5),
                    "is_verified": "true",
                }
            )
    with OUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"已写入 {len(rows)} 行时序夹具：{OUT_PATH}")


if __name__ == "__main__":
    main()
