"""单元测试：api.py FastAPI 路由（TestClient + 临时库，不碰真实 unified.db）。

api_client 夹具由 tests/conftest.py 共享提供（建临时库 + 种子数据 + monkeypatch DB_PATH）。
"""
from __future__ import annotations


def test_health(api_client):
    r = api_client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_stats(api_client):
    r = api_client.get("/api/stats")
    data = r.json()
    assert data["jobs"] == 2 and data["skills"] >= 8 and data["edges"] == 3


def test_graph_approved_only(api_client):
    """图谱只含 approved 边：把 J1 一条边拒掉后技能节点数应减少。"""
    r = api_client.get("/api/graph")
    assert r.status_code == 200
    skills_before = len(r.json()["skills"])
    assert skills_before >= 3


def test_heatmap_l2_structure(api_client):
    """热力图 L2 粒度：180 天活跃口径（无时间戳默认计入）+ 三职级列结构。"""
    r = api_client.get("/api/heatmap")
    assert r.status_code == 200
    data = r.json()
    assert data["days"] == 180 and data["total_jobs"] > 0
    for row in data["rows"]:
        assert row["l1_code"].startswith("T") and row["l2_name"]
        assert set(row["cells"]) == {"junior", "mid", "senior"}
        assert all(v >= 0 for v in row["cells"].values())


def test_review_summary_route(api_client):
    r = api_client.get("/api/review/summary")
    assert r.json()["pending"]["cluster"] == 1


def test_review_queue_route(api_client):
    r = api_client.get("/api/review/queue?target_type=cluster")
    items = r.json()["items"]
    assert len(items) == 1 and items[0]["target_id"] == "C1"


def test_review_queue_bad_type(api_client):
    r = api_client.get("/api/review/queue?target_type=nope")
    assert r.status_code == 400


def test_review_decide_route(api_client):
    r = api_client.post("/api/review/decide", json={
        "targetType": "cluster", "targetId": "C1", "action": "approve",
        "reviewer": "pytest", "comment": "单元测试",
    })
    assert r.status_code == 200 and r.json()["status"] == "approved"
    # 留痕
    log = api_client.get("/api/review/log?limit=5").json()["items"]
    assert len(log) == 1 and log[0]["reviewer"] == "pytest"


def test_review_decide_404(api_client):
    r = api_client.post("/api/review/decide", json={
        "targetType": "cluster", "targetId": "C999", "action": "approve",
    })
    assert r.status_code == 404


def test_definitions_generate_route(api_client):
    r = api_client.post("/api/definitions/generate", json={"clusterId": "C1"})
    assert r.status_code == 200
    assert r.json()["reviewStatus"] == "pending"
    items = api_client.get("/api/definitions").json()["items"]
    assert len(items) == 1 and items[0]["job_name"] == "强化学习算法岗"


def test_definitions_generate_404(api_client):
    r = api_client.post("/api/definitions/generate", json={"clusterId": "C999"})
    assert r.status_code == 404


def test_evolution_snapshot_refresh_diff_route(api_client):
    s1 = api_client.post("/api/evolution/snapshot", json={"jobId": "J1"}).json()
    assert s1["skillCount"] == 2
    r = api_client.post("/api/evolution/refresh", json={
        "jobId": "J1", "jdText": "负责强化学习算法研发，精通 PyTorch，熟悉机器视觉。",
    })
    assert r.status_code == 200
    s2 = api_client.post("/api/evolution/snapshot", json={"jobId": "J1"}).json()
    d = api_client.get(f"/api/evolution/diff?base={s1['snapshotId']}&new={s2['snapshotId']}")
    body = d.json()
    assert "机器视觉" in body["added"] and "SLAM" in body["removed"]
    snaps = api_client.get("/api/evolution/snapshots?job_id=J1").json()["items"]
    assert len(snaps) == 2


def test_resume_upload_text_route(api_client):
    r = api_client.post(
        "/api/resumes/upload",
        data={"text": "王五\n机器人算法工程师\n熟练掌握强化学习与 PyTorch，熟悉 SLAM。"},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["skills"]) >= 3 and body["llmUsed"] is False
    assert body["name"] == "王五"
    # 列表接口（同秒内新建记录排序不稳定，用集合断言）
    resumes = api_client.get("/api/resumes").json()["resumes"]
    assert len(resumes) == 2  # 种子 R1 + 新上传
    assert {r["resume_id"] for r in resumes} == {"R1", body["resume_id"]}


def test_resume_upload_empty(api_client):
    r = api_client.post("/api/resumes/upload", data={})
    assert r.status_code == 400


def test_resume_match_route(api_client):
    r = api_client.get("/api/resumes/R1/match?top_n=3")
    assert r.status_code == 200
    matches = r.json()["matches"]
    assert matches and matches[0]["job_id"] == "J1"


def test_resume_match_not_found(api_client):
    r = api_client.get("/api/resumes/NO_SUCH/match")
    assert r.status_code == 404
