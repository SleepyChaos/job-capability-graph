"""单元测试：extract.py 词典正则提取（含证据溯源与子词回溯）。"""
from __future__ import annotations

from pipeline.extract import (
    compile_skills,
    extract_one,
    normalize_text,
    build_term_pattern,
)


def test_normalize_text_fullwidth_to_halfwidth():
    # 全角标点转半角、括号转空格、小写化（具体转换规则以 normalize_text 实现为准）
    assert normalize_text("强化学习，PyTorch（测试）") == "强化学习 pytorch 测试"
    assert normalize_text(None) == ""


def test_build_term_pattern_comb_word():
    main, subs = build_term_pattern("ROS/激光雷达", "组合词")
    assert main is not None
    assert len(subs) >= 1


def test_extract_one_basic_hit(conn):
    records = compile_skills(conn)
    hits = extract_one("负责强化学习算法研发，精通 PyTorch。", records)
    terms = [h["skill_id"] for h in hits]
    # 强化学习 与 PyTorch 应命中（技能词从夹具种子加载）
    from pipeline import db as pdb
    sid_rl = pdb.ensure_skill(conn, "强化学习", "强化学习", "细分词", None, None, "AI")
    sid_pt = pdb.ensure_skill(conn, "PyTorch", "PyTorch", "细分词", None, None, "AI")
    assert sid_rl in terms and sid_pt in terms
    # 证据片段应包含命中原文
    ev = next(h["evidence"] for h in hits if h["skill_id"] == sid_rl)
    assert "强化学习" in ev


def test_extract_one_evidence_window(conn):
    records = compile_skills(conn)
    text = "岗位要求：" + "熟悉" + "强化学习" + "框架" * 60
    hits = extract_one(text, records)
    assert len(hits) >= 1
    ev = hits[0]["evidence"]
    assert len(ev) <= 40 * 2 + 4 + 8  # EVIDENCE_WINDOW*2 + 词长余量


def test_extract_one_subterm_backtracking(conn):
    """长词命中区间内补发短词：'深度强化学习' 应同时补发 '强化学习'。"""
    records = compile_skills(conn)
    hits = extract_one("熟悉深度强化学习算法。", records)
    terms = {h["skill_id"] for h in hits}
    from pipeline import db as pdb
    sid_long = pdb.ensure_skill(conn, "深度强化学习", "深度强化学习", "组合词", None, None, "AI")
    sid_rl = pdb.ensure_skill(conn, "强化学习", "强化学习", "细分词", None, None, "AI")
    assert sid_long in terms
    assert sid_rl in terms  # 子词回溯补发


def test_extract_one_no_hit(conn):
    records = compile_skills(conn)
    hits = extract_one("负责行政与采购工作。", records)
    assert hits == []


def test_extract_one_dedup_same_span(conn):
    """同一技能词多次出现只记一次（matched 去重）。"""
    records = compile_skills(conn)
    hits = extract_one("会强化学习，且深入研究强化学习。", records)
    from pipeline import db as pdb
    sid_rl = pdb.ensure_skill(conn, "强化学习", "强化学习", "细分词", None, None, "AI")
    assert sum(1 for h in hits if h["skill_id"] == sid_rl) == 1
