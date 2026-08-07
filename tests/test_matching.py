"""单元测试：matching.py 混合匹配引擎（稀疏向量余弦 + L1 域 + Jaccard + 头衔）。"""
from __future__ import annotations

from backend.matching import (
    MatchingEngine,
    _severity,
    cosine_sparse,
    jaccard,
    normalize_sparse,
)


# ---- 数学工具 ----

def test_normalize_sparse():
    v = normalize_sparse({1: 3.0, 2: 4.0})
    assert abs(v[1] - 0.6) < 1e-6 and abs(v[2] - 0.8) < 1e-6
    assert normalize_sparse({}) == {}


def test_cosine_sparse():
    left = {1: 0.6, 2: 0.8}
    right = {1: 0.6, 2: 0.8}
    assert abs(cosine_sparse(left, right) - 1.0) < 1e-6
    assert cosine_sparse(left, {3: 1.0}) == 0.0
    assert cosine_sparse({}, right) == 0.0


def test_jaccard():
    assert jaccard({1, 2}, {2, 3}) == 1 / 3
    assert jaccard({1}, {2}) == 0.0
    assert jaccard(set(), {1}) == 0.0


# ---- 引擎 ----

def test_engine_loads_skills(conn):
    engine = MatchingEngine(conn)
    assert len(engine.skills) >= 8
    assert any(info["l1_code"] == "AI" for info in engine.skills.values())


def test_resume_profile(conn):
    engine = MatchingEngine(conn)
    vec, l1, ids = engine.resume_profile("R1")
    assert len(ids) == 2  # 种子简历 2 项技能
    assert l1.get("AI", 0) > 0


def test_match_top_result_is_j1(conn):
    """简历技能（强化学习/PyTorch）与 J1 重合，J1 应排第一。"""
    engine = MatchingEngine(conn)
    result = engine.match("R1", top_n=5, resume_title="算法工程师")
    assert len(result["matches"]) > 0
    assert result["matches"][0]["job_id"] == "J1"
    assert result["semantic_available"] is False  # 透明降级声明
    top = result["matches"][0]
    assert "强化学习" in top["shared"]
    assert top["title_score"] is not None


def test_match_without_title_component(conn):
    """未提供 resume_title：title 分量退出，结果仍按剩余分量归一化。"""
    engine = MatchingEngine(conn)
    result = engine.match("R1", top_n=5)
    top = result["matches"][0]
    assert top["title_score"] is None
    assert 0 <= top["score"] <= 1


def test_match_l1_filter(conn):
    """给简历补一条 T1 域技能（ROS）后，限定 T1 只应返回 J2（SLAM/ROS 岗位）。"""
    ros_id = conn.execute(
        "SELECT skill_id FROM skills WHERE skill_term='ROS'"
    ).fetchone()["skill_id"]
    conn.execute(
        "INSERT INTO resume_skills (resume_id, skill_id, confidence, source) "
        "VALUES ('R1', ?, 0.95, 'dictionary')",
        (ros_id,),
    )
    conn.commit()
    engine = MatchingEngine(conn)
    result = engine.match("R1", top_n=5, l1_filter="T1")
    assert result["matches"]
    assert all(m["job_id"] == "J2" for m in result["matches"])


def test_match_empty_resume(conn):
    engine = MatchingEngine(conn)
    result = engine.match("NO_SUCH_RESUME")
    assert result["matches"] == []
    assert "warning" in result


def test_severity_bands():
    assert _severity(0, 5) == "minor"
    assert _severity(2, 5) == "moderate"
    assert _severity(3, 5) == "severe"
    assert _severity(1, 0) == "minor"
