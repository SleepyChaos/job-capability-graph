"""数据管线一键执行：词典 → JD 导入 → 提取 → 聚类 → 分类（阶段 1 闭环）。

用法（在项目根目录 job-capability-graph/ 下执行）：
  python -m pipeline.run_pipeline                  # 全流程（无 JD 文件时自动生成样例）
  python -m pipeline.run_pipeline --jobs a.xlsx    # 指定真实 JD 文件
  python -m pipeline.run_pipeline --skip-cluster   # 只跑到提取
"""
from __future__ import annotations

import argparse

from . import classify, cluster, config, db, extract, import_dictionary, import_jobs, make_sample_jds


def run(job_files: list[str] | None = None, skip_cluster: bool = False, reset: bool = False, l1: str | None = None) -> None:
    conn = db.connect()

    print("=" * 60)
    print("[1/5] 初始化统一数据库" + ("（--reset 全量重建）" if reset else ""))
    db.init_db(conn, reset=reset)

    print("=" * 60)
    print("[2/5] 导入技术词词典（统一技能本体）")
    import_dictionary.import_dictionary(conn, config.DICTIONARY_FILES)
    n_skills = conn.execute("SELECT COUNT(*) AS c FROM skills").fetchone()["c"]
    print(f"本体技能词: {n_skills}")

    print("=" * 60)
    print("[3/5] 导入 JD")
    if not job_files:
        sample_csv, _ = make_sample_jds.generate(n=120)
        job_files = [sample_csv]
        if l1 is None:
            l1 = "AI,BD,IOT,IS"  # 样例数据为新一代信息技术域，限定词典域避免存量词误提
    for fp in job_files:
        inserted, skipped = import_jobs.import_file(conn, fp)
        print(f"  {fp}: 导入 {inserted}，去重跳过 {skipped}")
    from datetime import datetime, timezone
    db.set_meta(conn, "last_imported_at", datetime.now(timezone.utc).isoformat())
    n_jobs = conn.execute("SELECT COUNT(*) AS c FROM jobs").fetchone()["c"]
    print(f"jobs 总量: {n_jobs}")

    print("=" * 60)
    print("[4/5] 词典正则提取技术词")
    extract.run_extraction(conn, l1_filter=l1)

    if skip_cluster:
        print("跳过聚类（--skip-cluster）")
        conn.close()
        return

    print("=" * 60)
    print("[5/5] 岗位动态聚类 + 分类映射")
    cluster.run_clustering(conn)
    n_cls = classify.run_classification(conn)
    print(f"分类完成: {n_cls} 个聚类")

    # 汇总
    print("=" * 60)
    summary = conn.execute(
        """
        SELECT (SELECT COUNT(*) FROM jobs) AS jobs,
               (SELECT COUNT(*) FROM job_skills) AS edges,
               (SELECT COUNT(*) FROM clusters) AS clusters,
               (SELECT COUNT(*) FROM skills) AS skills
        """
    ).fetchone()
    print(f"管线完成：岗位 {summary['jobs']}，图谱边 {summary['edges']}，"
          f"聚类 {summary['clusters']}，技能词 {summary['skills']}")
    conn.close()

    # 评测（有真值时）
    truth = config.DATA_DIR / "sample_ground_truth.json"
    if truth.exists():
        from .eval_extraction import evaluate
        evaluate(str(truth))


def main() -> None:
    parser = argparse.ArgumentParser(description="阶段1 数据管线一键执行")
    parser.add_argument("--jobs", nargs="*", default=None, help="JD Excel/CSV 文件（缺省用样例数据）")
    parser.add_argument("--skip-cluster", action="store_true", help="只执行到提取，不聚类")
    parser.add_argument("--reset", action="store_true", help="清空重建统一库")
    parser.add_argument("--l1", default=None, help="限定提取词典的 L1 域（逗号分隔）")
    args = parser.parse_args()
    run(job_files=args.jobs, skip_cluster=args.skip_cluster, reset=args.reset, l1=args.l1)


if __name__ == "__main__":
    main()
