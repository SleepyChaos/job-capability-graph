"""单元测试：api.py 工具函数（级别推导 / 技能类型 / 列表容错解析）。"""
from __future__ import annotations

from backend.api import derive_level, parse_list_field, skill_type_of


def test_derive_level():
    assert derive_level("3年以下") == "junior"
    assert derive_level("3-5年") == "mid"
    assert derive_level("5年以上") == "senior"
    assert derive_level("不限") == "mid"  # 无数字 → 默认中级
    assert derive_level(None) == "mid"


def test_skill_type_of():
    assert skill_type_of("PyTorch") == "tool"
    assert skill_type_of("Docker") == "tool"
    assert skill_type_of("沟通能力") == "soft"
    assert skill_type_of("数据治理") == "domain"
    assert skill_type_of("强化学习") == "hard"


def test_parse_list_field():
    assert parse_list_field('["a", "b"]') == ["a", "b"]
    assert parse_list_field("a, b，c") == ["a", "b", "c"]
    assert parse_list_field("[broken") == ["[broken"]
    assert parse_list_field("") == []
    assert parse_list_field(None) == []
