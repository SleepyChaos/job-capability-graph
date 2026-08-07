"""单元测试：resume_parse.py 简历解析（PDF 文本层 / 词典提取 / 姓名兜底 / LLM 降级）。"""
from __future__ import annotations

import pytest

from pipeline.resume_parse import (
    _map_term_to_skill,
    build_term_index,
    parse_resume,
    pdf_to_text,
)


def _make_minimal_pdf(text: str) -> bytes:
    """手工构造带文本层（BT/Tj）的最小 PDF，验证 pypdf 提取链路。"""
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj",
        f"4 0 obj << /Length {len(content)} >> stream\n{content}\nendstream endobj".encode(),
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
    ]
    body = b"\n".join(objects)
    xref_pos = 0
    out = [b"%PDF-1.4\n", body, b"\nxref\n0 6\n"]
    out.append(b"0000000000 65535 f \n")
    pos = len(b"%PDF-1.4\n")
    for obj in objects:
        out.append(f"{pos:010d} 00000 n \n".encode())
        pos += len(obj) + 1
    out.append(b"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n")
    out.append(str(pos).encode() + b"\n%%EOF\n")
    return b"".join(out)


def test_pdf_to_text():
    text = pdf_to_text(_make_minimal_pdf("ROS SLAM PyTorch"))
    assert "ROS" in text and "SLAM" in text and "PyTorch" in text


def test_parse_resume_extracts_skills(conn):
    result = parse_resume(
        conn,
        "李雷\n机器人算法工程师\n熟练掌握强化学习，熟悉 PyTorch 与深度学习，参与过 SLAM 项目。",
    )
    assert result["name"] == "李雷"  # 姓名兜底（首行）
    assert len(result["skill_ids"]) >= 3
    assert result["llm_used"] is False  # 无 Key 自动降级纯词典
    # 落库校验
    rows = conn.execute(
        "SELECT s.skill_term FROM resume_skills rs JOIN skills s "
        "ON rs.skill_id = s.skill_id WHERE rs.resume_id = ?",
        (result["resume_id"],),
    ).fetchall()
    terms = {r["skill_term"] for r in rows}
    assert "强化学习" in terms and "PyTorch" in terms


def test_parse_resume_empty_text(conn):
    with pytest.raises(ValueError):
        parse_resume(conn, "   ")


def test_parse_resume_name_first_line_only_when_short(conn):
    result = parse_resume(conn, "这是一个超过十二个字符的姓名行很长\n然后才是正文，会强化学习")
    assert result["name"] != "这是一个超过十二个字符的姓名行很长"  # 过长不兜底


def test_term_index_maps_llm_terms(conn):
    idx = build_term_index(conn)
    assert _map_term_to_skill("PyTorch", idx) is not None
    assert _map_term_to_skill("不存在的技能词XYZ", idx) is None
