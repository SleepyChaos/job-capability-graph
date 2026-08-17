"""窗口 A-1:从 Docker MySQL 导出抽取质量审计所需的只读数据快照。

真实数据在主检出目录的 Docker MySQL 里(无宿主端口映射),必须从
``/Users/chaos/Documents/QoderCN/2026-08-06/chat-1/job-capability-graph``
执行 ``docker compose exec mysql``(见 docs/08-抽取质量评估交接.md §2.4)。

本脚本把 backend/tools/audit_sql/ 下的 SELECT 语句逐个送进容器执行,
以 mysql --batch TSV 落盘到输出目录(默认 <repo>/.audit-data/,已本地排除)。
所有 SQL 均为只读 SELECT;不触碰本地 SQLite。

口径(内嵌,保证重跑同数字):
- 解析运行 run_code = jdparse_e7328e6370fbee62e79d2098(run_id=3)
- 词表版本 taxonomy v1.1(taxonomy_version_id=1)
- 该 run 无任何 LLM 回写(LLM 复核 4 次运行全部针对 run_id=1)

用法(在审计 worktree 下):
    python backend/tools/audit_export_extraction_data.py \
        --project-dir /Users/chaos/Documents/QoderCN/2026-08-06/chat-1/job-capability-graph
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

RUN_CODE = "jdparse_e7328e6370fbee62e79d2098"

# 与快照核对过的行数,仅用于打印对照;不符时给出警告但不中断(口径漂移应显式暴露)
EXPECTED_ROWS: dict[str, int | None] = {
    "01_alias_hits.tsv": 7591,
    "02_alias_inventory.tsv": 1872,
    "03_ambiguity_contexts.tsv": 1076,  # 735 needs_review + 341 context_confirmed
    "04_jd_corpus.tsv": None,
    "05_llm_reassessment.tsv": 735,
    "06_taxonomy_nodes.tsv": 2151,
    "07_job_code_map.tsv": 3718,
}

MYSQL_ARGS = [
    "mysql",
    "--default-character-set=utf8mb4",
    "-uapp",
    "-papp_password_change_me",
    "job_capability_graph",
    "--batch",
]


def export_one(project_dir: Path, sql_path: Path, out_path: Path) -> int:
    sql = sql_path.read_text(encoding="utf-8")
    cmd = ["docker", "compose", "exec", "-T", "mysql", *MYSQL_ARGS]
    proc = subprocess.run(
        cmd,
        cwd=project_dir,
        input=sql.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode("utf-8", errors="replace"))
        raise SystemExit(f"导出失败:{sql_path.name}(exit={proc.returncode})")
    text = proc.stdout.decode("utf-8")
    data_lines = [line for line in text.splitlines() if line]
    if not data_lines:
        raise SystemExit(f"导出结果为空:{sql_path.name}")
    out_path.write_bytes(proc.stdout)
    return len(data_lines) - 1  # 去掉表头


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path("/Users/chaos/Documents/QoderCN/2026-08-06/chat-1/job-capability-graph"),
        help="docker compose 主检出目录(MySQL 容器所在)",
    )
    parser.add_argument(
        "--sql-dir", type=Path, default=repo_root / "backend" / "tools" / "audit_sql"
    )
    parser.add_argument("--out-dir", type=Path, default=repo_root / ".audit-data")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    print(f"run_code={RUN_CODE} project_dir={args.project_dir}")
    ok = True
    for sql_path in sorted(args.sql_dir.glob("*.sql")):
        out_path = args.out_dir / (sql_path.stem + ".tsv")
        rows = export_one(args.project_dir, sql_path, out_path)
        digest = hashlib.sha256(out_path.read_bytes()).hexdigest()[:12]
        expected = EXPECTED_ROWS.get(out_path.name)
        flag = ""
        if expected is not None and rows != expected:
            flag = f"  !! 预期 {expected} 行,请核对口径"
            ok = False
        print(f"{out_path.name:<30} rows={rows:<6} sha256={digest}{flag}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
