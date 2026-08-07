"""单元测试：evolution.py 岗位定义生成与快照差分（能力动态更新）。"""
from __future__ import annotations

import pytest

from backend.evolution import (
    _parse_list,
    diff_snapshots,
    generate_definition,
    list_definitions,
    list_snapshots,
    refresh_skills,
    take_snapshot,
)


def test_parse_list_json_and_comma():
    assert _parse_list('["ARM 开发", "CoAP"]') == ["ARM 开发", "CoAP"]
    assert _parse_list("SLAM, ROS, 路径规划") == ["SLAM", "ROS", "路径规划"]
    assert _parse_list(None) == []


def test_generate_definition_heuristic_fallback(conn):
    """无 LLM Key 时降级启发式：定义字段来自真实聚类数据，状态 pending。"""
    result = generate_definition(conn, "C1")
    assert result["llmUsed"] is False
    assert result["reviewStatus"] == "pending"
    defs = list_definitions(conn)
    assert len(defs) == 1
    d = defs[0]
    assert d["job_name"] == "强化学习算法岗"
    assert "强化学习" in d["required_skills"]
    assert d["generation_source"] == "heuristic"
    assert d["review_status"] == "pending"


def test_generate_definition_cluster_not_found(conn):
    with pytest.raises(KeyError):
        generate_definition(conn, "C999")


def test_snapshot_and_diff_full_cycle(conn):
    """快照 → 更新 JD 重提取 → 快照 → 差分：新增/删除/修改标注。"""
    s1 = take_snapshot(conn, "J1", "更新前")
    assert s1["skillCount"] == 2

    # 更新 JD：去掉 SLAM，新增机器视觉，保留 PyTorch（改证据）
    new_jd = "负责强化学习算法研发，精通 PyTorch，熟悉机器视觉。"
    refresh_skills(conn, "J1", new_jd)
    s2 = take_snapshot(conn, "J1", "更新后")

    d = diff_snapshots(conn, s1["snapshotId"], s2["snapshotId"])
    assert "机器视觉" in d["added"]
    assert "SLAM" in d["removed"]
    assert d["jobId"] == "J1"
    assert "新增能力" in d["updateNote"] and "移除能力" in d["updateNote"]

    # 快照差分留痕（新增/移除为必现类型，保留技能可能因证据变化记 modified）
    rows = conn.execute("SELECT * FROM snapshot_diffs").fetchall()
    assert len(rows) == len(d["added"]) + len(d["removed"]) + len(d["modified"])
    types = {r["change_type"] for r in rows}
    assert {"added", "removed"} <= types <= {"added", "removed", "modified"}


def test_snapshot_unknown_job(conn):
    with pytest.raises(KeyError):
        take_snapshot(conn, "NO_SUCH_JOB")


def test_refresh_unknown_job(conn):
    with pytest.raises(KeyError):
        refresh_skills(conn, "NO_SUCH_JOB")


def test_refresh_empty_text(conn):
    with pytest.raises(ValueError):
        refresh_skills(conn, "J1", "   ")


def test_diff_unknown_snapshot(conn):
    with pytest.raises(KeyError):
        diff_snapshots(conn, 999, 998)


def test_list_snapshots_filter(conn):
    take_snapshot(conn, "J1", "v1")
    take_snapshot(conn, "J2", "v1")
    items = list_snapshots(conn, job_id="J1")
    assert len(items) == 1 and items[0]["jobId"] == "J1"
    assert len(list_snapshots(conn)) == 2
