"""设置 API 测试：LLM 配置读写、Key 掩码、连接测试降级（不真实外呼）。"""
from __future__ import annotations


def test_settings_llm_get_masked(api_client, monkeypatch):
    from pipeline import config as cfg

    monkeypatch.setattr(cfg, "LLM_API_KEY", "sk-1234567890abcdef")
    r = api_client.get("/api/settings/llm")
    assert r.status_code == 200
    data = r.json()
    assert data["configured"] is True
    assert data["keyMasked"] == "sk-***ef"  # 掩码：前 3 + 后 2
    assert "1234567890abcdef" not in r.text  # 完整 Key 不外泄


def test_settings_llm_get_empty(api_client):
    r = api_client.get("/api/settings/llm")
    assert r.json()["configured"] is False
    assert r.json()["keyMasked"] == ""


def test_settings_llm_save_updates_runtime(api_client, tmp_path, monkeypatch):
    """保存后内存配置立即生效，并回写 .env（测试用临时目录隔离）。"""
    from pipeline import config as cfg

    fake_env = tmp_path / ".env"
    fake_env.write_text("# head\nOPENAI_API_KEY=old\nOTHER=keep\n", encoding="utf-8")
    monkeypatch.setattr(cfg, "ROOT", tmp_path)

    r = api_client.post("/api/settings/llm", json={
        "apiKey": "sk-new-key-000111", "baseUrl": "https://api.deepseek.com/v1", "model": "deepseek-chat",
    })
    assert r.status_code == 200 and r.json()["saved"] is True
    assert r.json()["configured"] is True
    assert cfg.LLM_API_KEY == "sk-new-key-000111"  # 内存立即生效

    content = fake_env.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-new-key-000111" in content  # 幂等更新原行
    assert "OTHER=keep" in content  # 不破坏其他行
    assert content.count("OPENAI_API_KEY") == 1  # 无重复键


def test_settings_llm_save_empty_key_keeps(api_client):
    """apiKey 缺省（None）时不改动 Key。"""
    from pipeline import config as cfg

    before = cfg.LLM_API_KEY
    r = api_client.post("/api/settings/llm", json={"model": "deepseek-chat"})
    assert r.status_code == 200
    assert cfg.LLM_API_KEY == before


def test_settings_llm_test_without_key(api_client):
    """未配置 Key 时连接测试返回 ok=False（不真实外呼）。"""
    r = api_client.post("/api/settings/llm/test")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False and "Key" in data["error"]


def test_settings_llm_test_with_key_success(api_client, monkeypatch):
    from pipeline import config as cfg
    from pipeline import llm

    monkeypatch.setattr(cfg, "LLM_API_KEY", "sk-fake")
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "正常")
    r = api_client.post("/api/settings/llm/test")
    assert r.json()["ok"] is True and r.json()["reply"] == "正常"


def test_settings_llm_test_with_key_failure(api_client, monkeypatch):
    from pipeline import config as cfg
    from pipeline import llm

    monkeypatch.setattr(cfg, "LLM_API_KEY", "sk-fake")
    monkeypatch.setattr(llm, "chat", lambda *a, **k: None)
    r = api_client.post("/api/settings/llm/test")
    assert r.json()["ok"] is False
