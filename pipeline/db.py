"""统一数据库访问层：所有管线步骤经此模块读写 unified.db，禁止各自建连接建表。"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from . import config


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# 存量库补列迁移（schema v1.2）：新库由 schema.sql 直接建出新列，
# 旧库在此幂等补列（列已存在时 ALTER 报错，容忍跳过）
_MIGRATE_COLUMNS: dict[str, list[str]] = {
    "job_definitions": [
        "technology_id TEXT",
        "job_type TEXT",
        "scores_json TEXT",
        "evidence_json TEXT",
    ],
}


def _migrate_columns(conn: sqlite3.Connection) -> None:
    for table, columns in _MIGRATE_COLUMNS.items():
        for column in columns:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column}")
            except sqlite3.OperationalError:
                pass  # duplicate column name：已迁移


def init_db(conn: sqlite3.Connection, reset: bool = False) -> None:
    """执行统一建表脚本（唯一建表入口）。reset=True 时先清空全部表。"""
    if reset:
        tables = [r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()]
        conn.execute("PRAGMA foreign_keys = OFF")
        for t in tables:
            conn.execute(f"DROP TABLE IF EXISTS {t}")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()
    schema = config.SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)
    _migrate_columns(conn)
    conn.commit()


def make_dedup_key(title: str, company: str, collect_time: str) -> str:
    """幂等去重键：title + company + collect_time 归一化（对应统一设计原则）。"""
    parts = [re.sub(r"\s+", "", str(x or "")).lower() for x in (title, company, collect_time)]
    return "|".join(parts)


def ensure_domain(conn: sqlite3.Connection, l1_code: str, l1_name: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO domains (l1_code, l1_name) VALUES (?, ?)", (l1_code, l1_name)
    )


def ensure_l2(conn: sqlite3.Connection, l1_code: str, l2_name: str) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO l2_categories (l1_code, l2_name) VALUES (?, ?)", (l1_code, l2_name)
    )
    row = conn.execute(
        "SELECT l2_id FROM l2_categories WHERE l1_code = ? AND l2_name = ?", (l1_code, l2_name)
    ).fetchone()
    return row["l2_id"]


def ensure_l3(conn: sqlite3.Connection, l2_id: int, l3_name: str) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO l3_categories (l2_id, l3_name) VALUES (?, ?)", (l2_id, l3_name)
    )
    row = conn.execute(
        "SELECT l3_id FROM l3_categories WHERE l2_id = ? AND l3_name = ?", (l2_id, l3_name)
    ).fetchone()
    return row["l3_id"]


def ensure_skill(
    conn: sqlite3.Connection,
    term: str,
    term_raw: str,
    l4_type: str,
    l2_id: int | None,
    l3_id: int | None,
    l1_code: str,
    source: str = "dictionary",
) -> int:
    conn.execute(
        """
        INSERT OR IGNORE INTO skills (skill_term, skill_term_raw, l4_type, l3_id, l2_id, l1_code, source)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (term, term_raw, l4_type, l3_id, l2_id, l1_code, source),
    )
    row = conn.execute("SELECT skill_id FROM skills WHERE skill_term = ?", (term,)).fetchone()
    return row["skill_id"]


def load_skills(conn: sqlite3.Connection) -> list[dict]:
    """读取完整技能本体（含 L2/L3 名称），供提取与聚类使用。"""
    rows = conn.execute(
        """
        SELECT s.skill_id, s.skill_term, s.skill_term_raw, s.l4_type, s.l1_code,
               c2.l2_name, c3.l3_name
        FROM skills s
        LEFT JOIN l2_categories c2 ON s.l2_id = c2.l2_id
        LEFT JOIN l3_categories c3 ON s.l3_id = c3.l3_id
        """
    ).fetchall()
    return [dict(r) for r in rows]


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO pipeline_meta (key, value, updated_at) VALUES (?, ?, datetime('now'))
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')
        """,
        (key, value),
    )
