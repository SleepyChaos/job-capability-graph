"""人岗诊断界面测试用例（阶段 3 交付验证）。

以"前端 matching 页用户旅程"为粒度，用 TestClient 模拟页面一次完整操作流
（粘贴/拖拽上传 → 技能徽章 → Top10 匹配卡片 → 差距清单 → 领域筛选 → 空态），
断言接口返回的数据结构正是页面渲染所依赖的字段。
"""
from __future__ import annotations

# 上传返回的技能徽章字段（前端渲染徽章所需）
BADGE_FIELDS = {"skill_term", "l1_code", "confidence", "source"}
# 匹配卡片渲染字段（前端 Top10 卡片 + 四分项进度条 + 三列差距所需）
CARD_FIELDS = {
    "job_id", "title", "company", "city", "salary", "score",
    "capability_score", "l1_score", "core_jaccard", "title_score",
    "coverage", "shared", "missing", "extra", "missing_severity",
}
SEVERITIES = {"minor", "moderate", "severe"}


def _upload(api_client, text: str) -> dict:
    r = api_client.post("/api/resumes/upload", data={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def test_ui_paste_text_upload_skill_badges(api_client):
    """旅程 1：页面"粘贴简历文本"→ 上传 → 技能徽章数据完整、字段齐全。"""
    body = _upload(api_client, "李四\n算法工程师\n熟练掌握强化学习与 PyTorch，熟悉机器视觉。")

    assert body["llmUsed"] is False            # 未配置 LLM Key 的透明降级声明
    assert body["name"] == "李四"               # 姓名兜底解析
    assert len(body["skills"]) >= 3
    for badge in body["skills"]:
        assert BADGE_FIELDS <= set(badge)      # 徽章所需字段一个不少
    rl = next(b for b in body["skills"] if b["skill_term"] == "强化学习")
    assert rl["l1_code"] == "AI" and rl["source"] == "dictionary"
    assert 0 <= rl["confidence"] <= 1


def test_ui_drag_drop_txt_file_upload(api_client):
    """旅程 2：页面"拖拽上传 .txt 文件"（multipart file）→ 解析成功。"""
    r = api_client.post(
        "/api/resumes/upload",
        files={"file": ("resume.txt", "王五\n机器人工程师\n熟悉 ROS 与 SLAM。".encode("utf-8"), "text/plain")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["resume_id"] and body["name"] == "王五"
    terms = {b["skill_term"] for b in body["skills"]}
    assert {"ROS", "SLAM"} <= terms


def test_ui_full_journey_upload_then_match(api_client):
    """旅程 3：完整操作流——上传新简历 → 立即匹配 Top10 → 卡片渲染字段齐全 + 差距三列。"""
    body = _upload(api_client, "赵六\n算法工程师\n熟练掌握强化学习与 PyTorch，熟悉机器视觉。")
    rid = body["resume_id"]

    r = api_client.get(f"/api/resumes/{rid}/match?top_n=10")
    assert r.status_code == 200
    data = r.json()
    assert data["semantic_available"] is False   # 语义模型未启用，透明声明
    assert data["resume_skill_count"] >= 3
    assert data["candidate_count"] >= 1
    assert data["matches"]

    top = data["matches"][0]
    assert top["job_id"] == "J1"                 # 与种子岗位技能重合最大者排第一
    assert CARD_FIELDS <= set(top)               # 页面卡片渲染字段完整
    for f in ("capability_score", "l1_score", "core_jaccard", "score"):
        assert 0 <= top[f] <= 1
    assert top["missing_severity"] in SEVERITIES
    # 差距清单语义：J1 边=强化学习+SLAM
    assert "强化学习" in top["shared"]
    assert "SLAM" in top["missing"]
    assert "PyTorch" in top["extra"]


def test_ui_gap_analysis_three_columns(api_client):
    """旅程 4：差距清单三列方向验证——shared/missing/extra 各自语义正确、严重度分档合理。"""
    body = _upload(api_client, "孙七\n机器人工程师\n熟悉 SLAM 与 ROS。")
    r = api_client.get(f"/api/resumes/{body['resume_id']}/match?top_n=10")
    by_job = {m["job_id"]: m for m in r.json()["matches"]}

    j1 = by_job["J1"]                            # J1 边=强化学习+SLAM
    assert j1["shared"] == ["SLAM"]              # 共同具备
    assert j1["missing"] == ["强化学习"]          # 岗位有、简历缺
    assert j1["extra"] == ["ROS"]                # 简历有、岗位无
    assert j1["missing_severity"] == "moderate"  # 缺失 1/2 = 50% → moderate 档

    j2 = by_job["J2"]                            # J2 边=ROS
    assert j2["shared"] == ["ROS"] and j2["missing"] == []
    assert j2["extra"] == ["SLAM"]
    assert j2["missing_severity"] == "minor"     # 无缺失 → minor 档


def test_ui_l1_domain_filter(api_client):
    """旅程 5：页面"领域筛选"控件——限定 T1 域后只返回具身智能方向岗位。"""
    body = _upload(api_client, "孙七\n机器人工程师\n熟悉 SLAM 与 ROS。")
    r = api_client.get(f"/api/resumes/{body['resume_id']}/match?top_n=10&l1=T1")
    assert r.status_code == 200
    matches = r.json()["matches"]
    assert matches and all(m["job_id"] == "J2" for m in matches)


def test_ui_empty_skill_state(api_client):
    """旅程 6：空态——简历无任何可识别技能时，匹配返回空列表 + warning（页面展示兜底提示）。"""
    body = _upload(api_client, "周八\n销售顾问\n你好，我是普通求职者，没有技术背景。")
    assert body["skills"] == []
    r = api_client.get(f"/api/resumes/{body['resume_id']}/match")
    data = r.json()
    assert data["matches"] == []
    assert data["resume_skill_count"] == 0
    assert "warning" in data


def test_ui_history_resume_then_match(api_client):
    """旅程 7：历史简历路径——左侧历史列表 → 选中 R1 → 详情 → 匹配，Top1 为种子 J1。"""
    lst = api_client.get("/api/resumes?limit=20").json()
    assert lst["total"] >= 1
    r1 = next(r for r in lst["resumes"] if r["resume_id"] == "R1")
    assert r1["skill_count"] == 2                # 列表页徽章计数

    detail = api_client.get("/api/resumes/R1").json()
    assert len(detail["skills"]) == 2

    m = api_client.get("/api/resumes/R1/match?top_n=5").json()
    top = m["matches"][0]
    assert top["job_id"] == "J1"
    assert "强化学习" in top["shared"] and top["title_score"] is not None
