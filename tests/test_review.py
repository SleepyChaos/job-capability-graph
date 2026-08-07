"""单元测试：review.py 审核状态机（证据溯源 + 置信度门限 + 未审核不入正式表）。"""
from __future__ import annotations

import pytest

from backend.review import (
    AUTO_APPROVE_CONF,
    decide,
    decide_status,
    log,
    queue,
    summary,
)


# ---- 状态机策略 ----

def test_decide_status_auto_approve():
    assert decide_status("dictionary", 0.95, True) == "approved"


def test_decide_status_llm_always_pending():
    assert decide_status("llm", 0.95, True) == "pending"


def test_decide_status_low_confidence_pending():
    assert decide_status("dictionary", 0.85, True) == "pending"


def test_decide_status_no_evidence_pending():
    assert decide_status("dictionary", 0.95, False) == "pending"


def test_policy_threshold():
    assert AUTO_APPROVE_CONF == 0.90


# ---- 队列 / 裁决 / 留痕 ----

def test_summary_pending_counts(conn):
    s = summary(conn)
    # 种子：C1 为 LLM 命名 pending，C2 heuristic approved；图谱边全部 approved
    assert s["pending"]["cluster"] == 1
    assert s["pending"]["edge"] == 0
    assert s["edges"]["approved"] == 3
    assert s["edges"]["evidenceCoverage"] == 1.0


def test_queue_cluster(conn):
    items = queue(conn, "cluster")
    assert len(items) == 1
    assert items[0]["target_id"] == "C1"
    assert items[0]["name_source"] == "llm"


def test_queue_definition_empty(conn):
    assert queue(conn, "definition") == []


def test_queue_unknown_type(conn):
    with pytest.raises(ValueError):
        queue(conn, "nope")


def test_decide_approve_cluster(conn):
    result = decide(conn, "cluster", "C1", "approve", reviewer="tester", comment="ok")
    assert result["status"] == "approved"
    status = conn.execute(
        "SELECT review_status FROM clusters WHERE cluster_id='C1'"
    ).fetchone()["review_status"]
    assert status == "approved"
    logs = log(conn)
    assert len(logs) == 1
    assert logs[0]["target_type"] == "cluster" and logs[0]["action"] == "approve"


def test_decide_reject_cluster(conn):
    decide(conn, "cluster", "C1", "reject", reviewer="tester")
    assert conn.execute(
        "SELECT review_status FROM clusters WHERE cluster_id='C1'"
    ).fetchone()["review_status"] == "rejected"


def test_decide_edge(conn):
    """图谱边复合主键 target_id=job_id|skill_id（取 J1 真实存在的边）。"""
    sid = conn.execute(
        "SELECT skill_id FROM job_skills WHERE job_id='J1' LIMIT 1"
    ).fetchone()["skill_id"]
    target = f"J1|{sid}"
    result = decide(conn, "edge", target, "reject", reviewer="tester")
    assert result["status"] == "rejected"
    assert conn.execute(
        "SELECT review_status FROM job_skills WHERE job_id='J1' AND skill_id=?", (sid,)
    ).fetchone()["review_status"] == "rejected"


def test_decide_not_found(conn):
    with pytest.raises(KeyError):
        decide(conn, "cluster", "C999", "approve")


def test_decide_bad_action(conn):
    with pytest.raises(ValueError):
        decide(conn, "cluster", "C1", "maybe")


def test_decide_bad_type(conn):
    with pytest.raises(ValueError):
        decide(conn, "nope", "x", "approve")
