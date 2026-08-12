"""离线刷新按日技术触发指标（设计 §11.4）。

用法：
    uv run python tools/refresh_daily_metrics.py

与热力图同一口径（45 天窗口、L2 投影），幂等重算当前成功聚类运行的指标。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.modules.graph.service import refresh_daily_trigger_metrics


def main() -> None:
    with SessionLocal() as db:
        rows = refresh_daily_trigger_metrics(db)
        print(f"按日触发指标已刷新：{rows} 行")


if __name__ == "__main__":
    main()
