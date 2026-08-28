"""回填候选的 support_job_count，使其与机械事实卡的 job_count 一致。

两者同源（都是本轮证据命中的 JD 数），但候选就地刷新时只重写了事实卡，
漏掉了 support_job_count 这一列，于是列表页（读列）与数据卡（读卡）
会对同一个候选给出两个不同的「支撑 JD」。修复在
`_upsert_candidate` 的刷新分支，本脚本处理修复前已经写歪的存量数据。

事实卡是权威值：它随最近一次运行重写，而 support_job_count 停在首次发现。
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db.session import SessionLocal
# 候选表对 biz_job_role 有外键，映射器在 flush 时才解析它；
# 不导入岗位模型，commit 会报 NoReferencedTableError。
from app.modules.clustering.models import JobRole  # noqa: F401
from app.modules.discovery.models import EmergingRoleCandidate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="不加则只报告差异")
    args = parser.parse_args()

    with SessionLocal() as db:
        drifted = []
        for candidate in db.scalars(select(EmergingRoleCandidate)):
            card = candidate.mechanical_card_json or {}
            if "job_count" not in card:
                continue
            fresh = int(card["job_count"])
            if candidate.support_job_count != fresh:
                drifted.append((candidate.candidate_code, candidate.support_job_count, fresh))
                if args.apply:
                    candidate.support_job_count = fresh
        for code, before, after in drifted[:20]:
            print(f"{code}  {before} -> {after}")
        if len(drifted) > 20:
            print(f"…另有 {len(drifted) - 20} 条")
        print(f"共 {len(drifted)} 条不一致")
        if args.apply:
            db.commit()
            print("已回填")
        else:
            print("未落库，加 --apply 执行")


if __name__ == "__main__":
    main()
