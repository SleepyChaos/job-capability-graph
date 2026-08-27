"""生成合成简历评测集（测试数据集设计方案 §6.1、§15 public_synthetic）。

用法：
    uv run python tools/generate_synthetic_resumes.py [--count 30]

输出：
    data/test/resume_parsing/test_inputs/   简历文件（txt/docx/pdf）
    data/test/resume_parsing/test_gold/     每份简历的金标准 JSON
    data/test/resume_parsing/manifest.json  清单（含 sha256）

合成简历不来自任何真实个人；金标准技能取自已发布 L3 技术主数据。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.modules.taxonomy.models import TechnologyNode  # noqa: E402

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = REPOSITORY_ROOT / "data" / "test" / "resume_parsing" / "test_inputs"
GOLD_DIR = REPOSITORY_ROOT / "data" / "test" / "resume_parsing" / "test_gold"

SYNTHETIC_NAMES = [f"合成求职者{i:03d}" for i in range(1, 61)]
TARGET_ROLES = [
    "机器人感知算法工程师",
    "运动规划算法工程师",
    "机器人系统工程师",
    "具身智能数据工程师",
    "机器人控制算法工程师",
]
DEGREES = ["本科", "硕士", "博士"]
MAJORS = ["自动化", "控制科学与工程", "计算机科学与技术", "机械工程", "人工智能"]


def _load_l3_terms(limit: int) -> list[tuple[str, str]]:
    with SessionLocal() as db:
        rows = db.execute(
            select(TechnologyNode.technology_code, TechnologyNode.technology_name)
            .where(
                TechnologyNode.level_code == "L3",
                TechnologyNode.governance_status_code == "active",
            )
            .order_by(TechnologyNode.technology_code)
            .limit(limit)
        ).all()
    return [(code, name) for code, name in rows]


def _evidence_sentence(skill_name: str) -> str:
    templates = [
        f"负责{skill_name}模块开发，完成功能验证与性能优化。",
        f"在项目中使用{skill_name}解决关键工程问题，并沉淀可复用组件。",
        f"主导{skill_name}相关方案设计与真机联调，输出测试报告。",
    ]
    return random.choice(templates)


def _build_resume(index: int, terms: list[tuple[str, str]], fmt: str) -> dict:
    if fmt == "pdf":
        pool = [item for item in terms if item[1].isascii() and len(item[1]) >= 2]
        if len(pool) < 3:
            fmt = "docx"
            pool = terms
    else:
        pool = terms
    skill_count = random.randint(3, min(6, len(pool)))
    skills = random.sample(pool, skill_count)
    resume = {
        "sample_id": f"syn_resume_{index:04d}",
        "display_name": SYNTHETIC_NAMES[(index - 1) % len(SYNTHETIC_NAMES)],
        "target_role": random.choice(TARGET_ROLES),
        "degree": random.choice(DEGREES),
        "major": random.choice(MAJORS),
        "skills": [
            {"term_code": code, "term_name": name, "evidence_text": _evidence_sentence(name)}
            for code, name in skills
        ],
    }
    return resume, fmt


def _resume_text(resume: dict) -> str:
    lines = [
        f"姓名：{resume['display_name']}",
        f"求职意向：{resume['target_role']}",
        f"教育经历：{resume['degree']} · {resume['major']}",
        "项目经历：",
    ]
    for skill in resume["skills"]:
        lines.append(skill["evidence_text"])
    lines.append("技术栈：" + "、".join(skill["term_name"] for skill in resume["skills"]))
    return "\n".join(lines)


def _write_txt(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _write_docx(path: Path, text: str) -> None:
    import docx

    document = docx.Document()
    for line in text.splitlines():
        document.add_paragraph(line)
    document.save(str(path))


def _write_pdf(path: Path, resume: dict) -> None:
    """最小合法文本 PDF（ASCII 内容），用于文本型 PDF 解析评测。"""
    lines = [
        f"Name: {resume['sample_id']}",
        f"Target: {resume['target_role']}",
        "Education: synthetic degree",
        "Skills:",
    ]
    for skill in resume["skills"]:
        safe = "".join(ch for ch in skill["term_name"] if ord(ch) < 128) or skill["term_code"]
        lines.append(f"- {safe} ({skill['term_code']})")
    content_lines = []
    y = 780
    for line in lines:
        escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        content_lines.append(f"BT /F1 11 Tf 50 {y} Td ({escaped}) Tj ET")
        y -= 18
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    buffer = io.BytesIO()
    buffer.write(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(buffer.tell())
        buffer.write(f"{index} 0 obj\n".encode())
        buffer.write(obj)
        buffer.write(b"\nendobj\n")
    xref_pos = buffer.tell()
    buffer.write(f"xref\n0 {len(objects) + 1}\n".encode())
    buffer.write(b"0000000000 65535 f \n")
    for offset in offsets:
        buffer.write(f"{offset:010d} 00000 n \n".encode())
    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n"
    )
    buffer.write(trailer.encode())
    path.write_bytes(buffer.getvalue())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20260812)
    args = parser.parse_args()
    random.seed(args.seed)

    terms = _load_l3_terms(limit=120)
    if len(terms) < 10:
        raise SystemExit("L3 技术点不足，无法生成合成简历评测集")
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    manifest = []
    for index in range(1, args.count + 1):
        fmt = "txt" if index % 3 == 1 else ("docx" if index % 3 == 2 else "pdf")
        resume, fmt = _build_resume(index, terms, fmt)
        filename = f"{resume['sample_id']}.{fmt}"
        path = INPUT_DIR / filename
        text = _resume_text(resume)
        if fmt == "txt":
            _write_txt(path, text)
        elif fmt == "docx":
            _write_docx(path, text)
        else:
            _write_pdf(path, resume)
        gold = {
            "sample_id": resume["sample_id"],
            "file": filename,
            "format": fmt,
            "privacy_level": "public_synthetic",
            "target_job_titles": [resume["target_role"]],
            "education": [{"degree": resume["degree"], "major": resume["major"]}],
            "skills": [
                {
                    "term_code": skill["term_code"],
                    "term_name": skill["term_name"],
                    "evidence_text": skill["evidence_text"],
                    "level": "applied",
                }
                for skill in resume["skills"]
            ],
            "unsupported_inferences": [],
        }
        (GOLD_DIR / f"{resume['sample_id']}.json").write_text(
            json.dumps(gold, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        manifest.append(
            {
                "sample_id": resume["sample_id"],
                "file": filename,
                "format": fmt,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )

    manifest_payload = {
        "dataset_id": "resume_parsing_synthetic_v1",
        "version": "1.0.0",
        "status": "frozen_synthetic",
        "privacy_level": "public_synthetic",
        "sample_count": len(manifest),
        "items": manifest,
    }
    (REPOSITORY_ROOT / "data" / "test" / "resume_parsing" / "manifest.json").write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"已生成 {len(manifest)} 份合成简历（txt/docx/pdf 混合）与金标准。")


if __name__ == "__main__":
    main()
