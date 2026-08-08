"""阶段三测试：技术演化驱动的新兴岗位发现引擎（pipeline/emerging.py）。

覆盖：成熟度计算、任务缺口评分、provider 降级、运行持久化、提交审核闭环、API 路由。
"""
from __future__ import annotations

import json
from datetime import date

from pipeline import emerging


def seed_emerging(conn) -> None:
    """在 conftest.seed 之上补技术演化域种子（T9.01 测试技术）。"""
    conn.execute(
        "INSERT INTO technologies (technology_id, standard_name, level, domain, definition,"
        " parent_id, aliases_json, mapped_l1_code)"
        " VALUES ('T9.01', '测试技术', 'L2', '测试域', '用于单测的技术实体', NULL,"
        " '[\"强化学习\", \"PyTorch\"]', 'T1')"
    )
    conn.execute(
        "INSERT INTO milestones (event_id, name, description, event_date, source,"
        " technology_category, event_type, technology_links)"
        " VALUES ('E1', '测试技术开源发布', '核心框架开源', '2025-06-01', '官网',"
        " '测试类目', '开源发布', '[[\"T9\", 1.0]]'),"
        " ('E2', '测试技术未来事件', '尚未发生', '2099-01-01', '官网',"
        " '测试类目', '产品发布', '[[\"T9\", 1.0]]')"
    )
    conn.execute(
        "INSERT INTO capabilities (technology_code, name, object, scenario)"
        " VALUES ('T9.01', '应用{技术}形成新能力', '{技术}', '测试场景')"
    )
    conn.execute(
        "INSERT INTO tasks (technology_code, name, task_group, keywords_json, relevance)"
        " VALUES ('T9.01', '开发测试技术核心算法', 'model', '[\"强化学习\", \"算法\"]', 0.95),"
        " ('T9.01', '构建测试技术评测体系', 'evaluation', '[\"评测\"]', 0.9)"
    )
    conn.execute(
        "INSERT INTO role_titles (technology_code, task_group, title)"
        " VALUES ('T9.01', 'model', '测试技术算法工程师'), ('T9.01', 'evaluation', '测试技术评测工程师')"
    )
    conn.commit()


# ---------------------------------------------------------------------------
# 成熟度模型
# ---------------------------------------------------------------------------

def test_maturity_excludes_future_events_and_weights():
    events = [
        {"event_id": "E1", "event_date": "2025-06-01", "event_type": "开源发布", "relevance": 1.0},
        {"event_id": "E2", "event_date": "2099-01-01", "event_type": "产品发布", "relevance": 1.0},
    ]
    score, contributions = emerging.maturity_score(events, date(2026, 8, 1))
    assert 0 < score <= 0.98
    assert [c["event_id"] for c in contributions] == ["E1"]  # 未来事件不计入


def test_maturity_empty_events_zero():
    score, contributions = emerging.maturity_score([], date(2026, 8, 1))
    assert score == 0.0 and contributions == []


# ---------------------------------------------------------------------------
# Provider 降级与防幻觉过滤
# ---------------------------------------------------------------------------

def test_provider_llm_degrades_to_rule_without_key():
    provider = emerging.get_provider("llm")  # conftest 强制 LLM_API_KEY=""
    assert provider.origin == "library"


def test_provider_unknown_mode_falls_back_rule():
    assert emerging.get_provider("whatever").origin == "library"


def test_mock_provider_tasks_carry_keywords():
    tasks = emerging.MockProvider().extract_tasks({"standard_name": "X"}, [])
    assert tasks and all(t["keywords"] for t in tasks)  # 防幻觉：必须携带关键词


def test_llm_provider_filters_tasks_without_keywords(monkeypatch):
    from pipeline import llm

    monkeypatch.setattr(llm, "is_available", lambda: True)
    monkeypatch.setattr(
        llm, "chat_json", lambda *a, **k: [
            {"name": "有证据任务", "group": "model", "keywords": ["强化学习"], "relevance": 0.9},
            {"name": "无关键词任务", "group": "model", "keywords": [], "relevance": 0.9},
            {"name": "", "group": "data", "keywords": ["x"], "relevance": 0.9},
        ]
    )
    tasks = emerging.LLMProvider().extract_tasks({}, [])
    assert [t["name"] for t in tasks] == ["有证据任务"]


def test_llm_title_and_definition_parse():
    p = emerging.LLMProvider()
    title, definition = p._parse_title_and_definition(
        "岗位名称：柔性触觉感知算法工程师\n岗位定义：负责电子皮肤信号建模与感知算法研发。"
    )
    assert title == "柔性触觉感知算法工程师"
    assert "电子皮肤" in definition


def test_llm_title_invalid_falls_back_none():
    p = emerging.LLMProvider()
    title, _ = p._parse_title_and_definition("岗位名称：x\n岗位定义：定义文本")  # 名称过短
    assert title is None
    title2, _ = p._parse_title_and_definition("没有格式的输出文本")
    assert title2 is None


def test_run_llm_mode_sets_title_alias_and_submit_uses_it(conn, monkeypatch):
    """llm 模式：候选携带 job_title_alias；提交审核时 job_name 优先用 LLM 主名。"""
    from pipeline import llm

    seed_emerging(conn)
    monkeypatch.setattr(llm, "is_available", lambda: True)

    def fake_chat(messages, temperature=0.2, timeout=60):
        system = messages[0]["content"]
        if "岗位名称" in system:  # 命名+定义调用
            return "岗位名称：测试技术智能算法专家\n岗位定义：围绕测试技术的智能算法研发岗位。"
        return None

    monkeypatch.setattr(llm, "chat", fake_chat)
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: None)  # 任务动态生成不可用 → 走知识库

    payload = emerging.run_and_persist(conn, "T9.01", target_date="2026-08-01", generation_mode="llm")
    assert payload["result"]["generation_mode"] == "llm"
    cand = payload["result"]["candidate_jobs"][0]
    assert cand["job_title_alias"] == "测试技术智能算法专家"
    assert cand["job_definition"]  # 定义非空

    definition_id = emerging.submit_candidate(conn, payload["run_id"], cand["candidate_id"])
    row = conn.execute("SELECT job_name FROM job_definitions WHERE definition_id = ?", (definition_id,)).fetchone()
    assert row["job_name"] == "测试技术智能算法专家"  # 主名优先


def test_run_llm_mode_naming_failure_falls_back(conn, monkeypatch):
    """llm 命名解析失败：alias 为 None，提交回退规则组合名。"""
    from pipeline import llm

    seed_emerging(conn)
    monkeypatch.setattr(llm, "is_available", lambda: True)
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "格式错误的输出")
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: None)

    payload = emerging.run_and_persist(conn, "T9.01", target_date="2026-08-01", generation_mode="llm")
    cand = payload["result"]["candidate_jobs"][0]
    assert cand["job_title_alias"] is None
    assert cand["job_definition"]  # 定义回退规则模板

    definition_id = emerging.submit_candidate(conn, payload["run_id"], cand["candidate_id"])
    row = conn.execute("SELECT job_name FROM job_definitions WHERE definition_id = ?", (definition_id,)).fetchone()
    assert row["job_name"] == cand["job_title"]  # 回退规则名


# ---------------------------------------------------------------------------
# 完整链路：运行 → 持久化 → 提交审核
# ---------------------------------------------------------------------------

def test_run_and_persist_full_chain(conn):
    seed_emerging(conn)
    payload = emerging.run_and_persist(conn, "T9.01", target_date="2026-08-01")
    assert payload["status"] == "completed"
    result = payload["result"]

    # 候选岗位：任务组 model/evaluation 各一簇，七维得分与证据链齐全
    titles = {c["job_title"] for c in result["candidate_jobs"]}
    assert "测试技术算法工程师" in titles and "测试技术评测工程师" in titles
    cand = result["candidate_jobs"][0]
    assert cand["job_type"] in ("新兴岗位", "岗位演化", "已有岗位")
    assert set(cand["scores"]) == {
        "technology_relevance", "task_gap", "cohesion", "cross_company",
        "maturity", "evidence", "existing_overlap",
    }
    assert cand["evidence_path"][0]["type"] == "technology"
    assert cand["required_skills"] and cand["application_scenarios"]

    # model 任务关键词"强化学习"应召回 J1（证据分 ≥0.45）
    model_task = next(t for t in result["tasks"] if t["group"] == "model")
    assert model_task["job_mentions"] >= 1
    assert model_task["job_evidence"][0]["job_id"] == "J1"

    # 运行记录落库
    row = conn.execute(
        "SELECT status FROM emerging_runs WHERE run_id = ?", (payload["run_id"],)
    ).fetchone()
    assert row["status"] == "completed"


def test_run_unknown_technology_raises(conn):
    seed_emerging(conn)
    try:
        emerging.run_and_persist(conn, "NOPE")
        raise AssertionError("应当抛出 ValueError")
    except ValueError:
        pass
    # 失败也留痕
    row = conn.execute("SELECT status FROM emerging_runs WHERE technology_id = 'NOPE'").fetchone()
    assert row["status"] == "failed"


def test_submit_candidate_into_review(conn):
    seed_emerging(conn)
    payload = emerging.run_and_persist(conn, "T9.01", target_date="2026-08-01")
    candidate = payload["result"]["candidate_jobs"][0]
    definition_id = emerging.submit_candidate(conn, payload["run_id"], candidate["candidate_id"])

    row = conn.execute(
        "SELECT * FROM job_definitions WHERE definition_id = ?", (definition_id,)
    ).fetchone()
    assert row["review_status"] == "pending"  # 未审核不入正式表
    assert row["generation_source"] == "emerging"
    assert row["technology_id"] == "T9.01"
    assert json.loads(row["required_skills"])  # 五要素齐全
    assert json.loads(row["evidence_json"])["jobs"] is not None


def test_submit_unknown_candidate_raises(conn):
    seed_emerging(conn)
    payload = emerging.run_and_persist(conn, "T9.01", target_date="2026-08-01")
    try:
        emerging.submit_candidate(conn, payload["run_id"], "CAND-XXX-99")
        raise AssertionError("应当抛出 KeyError")
    except KeyError:
        pass


# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------

def test_api_emerging_routes(api_client):
    # TestClient 背后是 tmp 临时库，直接对其补技术演化域种子
    import sqlite3

    import backend.api as api_mod

    c = sqlite3.connect(api_mod.DB_PATH)
    c.row_factory = sqlite3.Row
    seed_emerging(c)
    c.close()

    r = api_client.get("/api/emerging/technologies/search", params={"q": "测试技术"})
    assert r.status_code == 200
    assert r.json()["items"][0]["technology_id"] == "T9.01"

    r = api_client.post("/api/emerging/run", json={
        "technologyId": "T9.01", "targetDate": "2026-08-01", "generationMode": "rule",
    })
    assert r.status_code == 200
    run_id = r.json()["run_id"]

    r = api_client.get(f"/api/emerging/runs/{run_id}")
    assert r.status_code == 200 and r.json()["status"] == "completed"
    candidate_id = r.json()["result"]["candidate_jobs"][0]["candidate_id"]

    r = api_client.post("/api/emerging/submit", json={"runId": run_id, "candidateId": candidate_id})
    assert r.status_code == 200 and r.json()["reviewStatus"] == "pending"

    # governance 审核队列可见该定义
    r = api_client.get("/api/review/queue", params={"target_type": "definition"})
    assert r.status_code == 200
    names = [item.get("job_name") for item in r.json()["items"]]
    assert any("测试技术" in (name or "") for name in names)

    r = api_client.get("/api/emerging/runs")
    assert r.json()["items"][0]["run_id"] == run_id


def test_api_emerging_run_invalid_technology(api_client):
    r = api_client.post("/api/emerging/run", json={"technologyId": "NOPE"})
    assert r.status_code == 422
