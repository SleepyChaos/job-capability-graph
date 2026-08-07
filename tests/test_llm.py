"""单元测试：llm.py OpenAI 兼容客户端（未配置 Key 时透明降级）。"""
from __future__ import annotations

from pipeline import config, llm


def test_extract_json_plain():
    assert llm.extract_json('{"name": "张三", "skills": ["ROS"]}') == {
        "name": "张三", "skills": ["ROS"],
    }


def test_extract_json_code_fence():
    text = '```json\n{"name": "李四"}\n```'
    assert llm.extract_json(text) == {"name": "李四"}


def test_extract_json_embedded():
    text = '说明文字：{"a": 1, "b": [2, 3]} 结尾'
    assert llm.extract_json(text) == {"a": 1, "b": [2, 3]}


def test_is_available_without_key(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    assert llm.is_available() is False


def test_chat_returns_none_without_key(monkeypatch):
    """未配置 Key：chat 必须返回 None（调用方降级，绝不抛异常）。"""
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    assert llm.chat([{"role": "user", "content": "hi"}]) is None


def test_chat_json_returns_none_without_key(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    assert llm.chat_json("sys", "user") is None
