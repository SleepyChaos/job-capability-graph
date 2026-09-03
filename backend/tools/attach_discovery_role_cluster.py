"""把已入库的推演派生岗位挂到最近的岗位聚类上。

**为什么需要这一步。** 候选审批入库时会建岗位、岗位版本与能力项，但不会建
`rel_job_cluster_role`——聚类是从真实 JD 归并出来的，而推演岗位没有 JD，流程里没有
天然的归属来源。结果是岗位在库里齐全，却在所有按聚类定位的图谱上无处安放：查得到，
看不见。本工具补的就是这一条链接。

**关系类型不能用 `represents`。** 那个码的含义是「该岗位代表这个簇」，而推演岗位并不
代表任何已观测的岗位群——它的立论前提恰恰是这组技术在招聘市场上从未同现。因此单独用
`discovery_nearest`：只声明「在现有聚类里，这个簇与它最近」，不声明代表关系。消费方按
`is_primary` 取数，不筛关系码，所以图谱照样能定位到它。

**最近簇怎么选。** 按岗位版本的能力项技术编码，统计各簇成员 JD 要求这些技术的次数，
取覆盖技术种类最多、其次命中次数最多的簇。命中为零时不挂——宁可继续看不见，也不要
把它安到一个毫无关系的簇上。

用法（backend 目录 / 容器内）：
    python -m tools.attach_discovery_role_cluster --role-code ROLE-N-EE73E9917A6A
    python -m tools.attach_discovery_role_cluster --role-code ROLE-N-EE73E9917A6A --execute
"""

from __future__ import annotations

import argparse

from sqlalchemy import text

from app.db.session import SessionLocal

RELATION_TYPE = "discovery_nearest"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="为推演派生岗位补聚类归属。")
    parser.add_argument("--role-code", required=True)
    parser.add_argument(
        "--clustering-run-code",
        default="cluster_8c34456a914d4e53bac8afa3",
        help="在哪一次聚类的簇里找最近簇；默认与候选生成时所用的一致",
    )
    parser.add_argument("--execute", action="store_true", help="真正落库（默认只预览）")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with SessionLocal() as db:
        role = db.execute(
            text(
                "SELECT job_role_id, canonical_name, origin_type_code "
                "FROM biz_job_role WHERE role_code = :code"
            ),
            {"code": args.role_code},
        ).one_or_none()
        if role is None:
            raise SystemExit(f"岗位不存在：{args.role_code}")
        role_id, role_name, origin = role
        if origin != "inference_derived":
            raise SystemExit(f"{args.role_code} 不是推演派生岗位（origin={origin}），本工具不处理")

        codes = [
            row[0]
            for row in db.execute(
                text(
                    """
                    SELECT DISTINCT n.technology_code
                    FROM rel_job_role_version_requirement q
                    JOIN biz_job_role_version v
                         ON v.job_role_version_id = q.job_role_version_id
                    JOIN md_technology_node n
                         ON n.technology_node_id = q.technology_node_id
                    WHERE v.job_role_id = :role_id
                    """
                ),
                {"role_id": role_id},
            )
        ]
        if not codes:
            raise SystemExit(f"{args.role_code} 的岗位版本没有能力项，无法判断最近簇")

        existing = db.execute(
            text("SELECT COUNT(*) FROM rel_job_cluster_role WHERE job_role_id = :role_id"),
            {"role_id": role_id},
        ).scalar_one()

        rows = db.execute(
            text(
                """
                SELECT cv.job_cluster_version_id, cv.cluster_label,
                       COUNT(DISTINCT n.technology_code) AS matched_codes,
                       COUNT(*) AS hits,
                       COUNT(DISTINCT m.job_posting_id) AS members
                FROM rel_job_cluster_member m
                JOIN biz_job_cluster_version cv
                     ON cv.job_cluster_version_id = m.job_cluster_version_id
                JOIN biz_job_requirement rq ON rq.job_posting_id = m.job_posting_id
                JOIN md_technology_node n ON n.technology_node_id = rq.technology_node_id
                WHERE cv.clustering_run_id = (
                          SELECT clustering_run_id FROM biz_job_clustering_run
                          WHERE run_code = :run_code
                      )
                  AND n.technology_code IN :codes
                GROUP BY cv.job_cluster_version_id, cv.cluster_label
                ORDER BY matched_codes DESC, hits DESC
                LIMIT 5
                """
            ).bindparams(),
            {"run_code": args.clustering_run_code, "codes": tuple(codes)},
        ).all()

        print(f"岗位：{args.role_code} {role_name}")
        print(f"能力项技术编码：{codes}")
        print(f"现有聚类归属：{existing} 条")
        if not rows:
            raise SystemExit("没有任何簇的成员 JD 要求这些技术，不挂——保持看不见胜过错挂")
        print("候选最近簇（按覆盖技术种类、命中次数排序）：")
        for item in rows:
            print(f"  {item[0]} {item[1]} · 覆盖 {item[2]}/{len(codes)} 种 · 命中 {item[3]} 次 · 成员 {item[4]}")

        best = rows[0]
        print(f"\n选定：{best[0]} {best[1]}")
        if not args.execute:
            print("（预览模式，未落库；加 --execute 生效）")
            return

        db.execute(
            text(
                """
                INSERT INTO rel_job_cluster_role
                    (job_cluster_version_id, job_role_id, relation_type_code,
                     confidence_score, is_primary)
                VALUES (:cluster_id, :role_id, :relation, :confidence, 1)
                ON DUPLICATE KEY UPDATE confidence_score = VALUES(confidence_score)
                """
            ),
            {
                "cluster_id": best[0],
                "role_id": role_id,
                "relation": RELATION_TYPE,
                # 置信度沿用候选的综合证据分，不另造一个分数。
                "confidence": float(
                    db.execute(
                        text(
                            "SELECT evidence_strength_score FROM biz_job_role_version "
                            "WHERE job_role_id = :role_id ORDER BY version_no DESC LIMIT 1"
                        ),
                        {"role_id": role_id},
                    ).scalar_one()
                    or 0
                ),
            },
        )
        db.commit()
        print("已写入 rel_job_cluster_role。")


if __name__ == "__main__":
    main()
