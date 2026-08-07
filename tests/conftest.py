"""pytest 共享夹具：内存级统一库（schema.sql 建表 + 种子数据）+ 临时库 TestClient。"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import db as pdb  # noqa: E402


def seed(conn: sqlite3.Connection) -> None:
    """最小种子：两域 × 8 技能词、2 岗位 + 图谱边、1 简历 + 技能、2 聚类。"""
    pdb.ensure_domain(conn, "AI", "人工智能")
    pdb.ensure_domain(conn, "T1", "具身智能·算法")

    l2 = pdb.ensure_l2(conn, "AI", "机器学习")
    l3 = pdb.ensure_l3(conn, l2, "强化学习")
    lid = pdb.ensure_skill(conn, "强化学习", "强化学习", "细分词", l2, l3, "AI")
    pdb.ensure_skill(conn, "深度学习", "深度学习", "细分词", l2, None, "AI")
    pdb.ensure_skill(conn, "PyTorch", "PyTorch", "细分词", l2, None, "AI")
    pdb.ensure_skill(conn, "深度强化学习", "深度强化学习", "组合词", l2, None, "AI")
    pdb.ensure_skill(conn, "机器视觉", "机器视觉", "细分词", l2, None, "AI")
    pdb.ensure_skill(conn, "SLAM", "SLAM", "细分词", l2, None, "T1")
    pdb.ensure_skill(conn, "ROS", "ROS", "细分词", l2, None, "T1")
    pdb.ensure_skill(conn, "路径规划", "路径规划", "细分词", l2, None, "T1")

    conn.execute(
        """
        INSERT INTO jobs (job_id, title, company, city, jd_text, salary_text, collect_time)
        VALUES ('J1', '强化学习算法工程师', '测试科技', '北京',
                '负责强化学习算法研发，精通 PyTorch，具备深度学习基础，熟悉 SLAM 与路径规划。',
                '30-50K', '2026-08-01'),
               ('J2', 'SLAM 开发工程师', '测试机器人', '深圳',
                '负责 ROS 环境下的 SLAM 系统开发，熟悉激光雷达与路径规划算法。',
                '25-40K', '2026-08-01')
        """
    )
    lid_ros = conn.execute("SELECT skill_id FROM skills WHERE skill_term='ROS'").fetchone()["skill_id"]
    lid_slam = conn.execute("SELECT skill_id FROM skills WHERE skill_term='SLAM'").fetchone()["skill_id"]
    conn.execute(
        """
        INSERT INTO job_skills (job_id, skill_id, evidence, confidence, l4_type, source, review_status)
        VALUES ('J1', ?, '精通 PyTorch', 0.95, '细分词', 'dictionary', 'approved'),
               ('J1', ?, '熟悉 SLAM 与路径规划', 0.95, '细分词', 'dictionary', 'approved'),
               ('J2', ?, 'ROS 环境下的 SLAM', 0.95, '细分词', 'dictionary', 'approved')
        """,
        (lid, lid_slam, lid_ros),
    )
    conn.execute(
        """
        INSERT INTO resumes (resume_id, name, title, skills_json, raw_text)
        VALUES ('R1', '张三', '算法工程师',
                '{"skills":["强化学习","PyTorch"]}',
                '张三\n算法工程师\n熟练掌握强化学习，熟悉 PyTorch 与深度学习。')
        """
    )
    conn.execute(
        "INSERT INTO resume_skills (resume_id, skill_id, confidence, source) "
        "VALUES ('R1', ?, 0.95, 'dictionary'), ('R1', ?, 0.95, 'dictionary')",
        (lid, pdb.ensure_skill(conn, "PyTorch", "PyTorch", "细分词", l2, None, "AI")),
    )
    conn.execute(
        """
        INSERT INTO clusters (cluster_id, cluster_name, description, shared_skills,
                              representative_titles, keywords, job_count, name_source, review_status)
        VALUES ('C1', '强化学习算法岗', '强化学习方向的岗位聚合', '强化学习, 深度学习, PyTorch',
                '强化学习算法工程师', '机器人, 具身智能', 5, 'llm', 'pending'),
               ('C2', 'SLAM 开发岗', 'SLAM 方向岗位聚合', 'SLAM, ROS, 路径规划',
                'SLAM 开发工程师', '激光雷达', 3, 'heuristic', 'approved')
        """
    )
    conn.execute(
        "INSERT INTO cluster_classifications (cluster_id, primary_l1_code, primary_l2_name) "
        "VALUES ('C1', 'AI', '机器学习'), ('C2', 'T1', '具身智能')"
    )
    conn.commit()


@pytest.fixture(autouse=True)
def llm_key_off(monkeypatch):
    """测试默认强制 LLM 无 Key（确定性降级路径、离线可跑）。

    接入真实 Key 后，业务用例仍按无 Key 降级路径断言；
    需要验证 LLM 路径的用例可自行 monkeypatch 覆盖。
    """
    from pipeline import config as cfg

    monkeypatch.setattr(cfg, "LLM_API_KEY", "")


@pytest.fixture()
def conn(tmp_path) -> sqlite3.Connection:
    """每个用例独立临时库：建表 + 种子数据。"""
    c = pdb.connect(tmp_path / "test.db")
    pdb.init_db(c)
    seed(c)
    yield c
    c.close()


@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    """FastAPI TestClient + 临时库（不碰真实 unified.db），供路由/界面旅程用例共享。"""
    import backend.api as api_mod

    c = pdb.connect(tmp_path / "api.db")
    pdb.init_db(c)
    seed(c)
    c.close()
    monkeypatch.setattr(api_mod, "DB_PATH", tmp_path / "api.db")
    return TestClient(api_mod.app)
