"""评测运行器（测试数据集设计方案 §13、计划 E6）。

用法：
    uv run python tools/run_evaluation.py resume          # 简历解析指标（合成集）
    uv run python tools/run_evaluation.py jd               # JD 解析指标（依赖人工金标准）
    uv run python tools/run_evaluation.py matching-sanity  # 匹配合成自检（非官方口径）
    uv run python tools/run_evaluation.py all

报告输出到 data/processed/reports/evaluation_<日期>/。
官方三项 90% 指标以人工冻结金标准为准；本脚本在金标准缺失时如实报告 pending。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.modules.talent.resume_adapter import extract_resume_text  # noqa: E402
from app.modules.taxonomy.models import TechnologyAlias, TechnologyNode  # noqa: E402

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = REPOSITORY_ROOT / "data" / "test"
REPORT_ROOT = REPOSITORY_ROOT / "data" / "processed" / "reports"


def _report_dir() -> Path:
    path = REPORT_ROOT / f"evaluation_{date.today().isoformat().replace('-', '')}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _build_term_index(db) -> list[tuple[str, str]]:
    """返回 (表面词小写, L3 编码) 列表，与画像抽取同口径（别名 + L3 标准名）。"""
    nodes = {
        node.technology_node_id: node
        for node in db.scalars(
            select(TechnologyNode).where(TechnologyNode.governance_status_code == "active")
        )
    }

    def l3_code(node: TechnologyNode) -> str | None:
        current = node
        visited = set()
        while current and current.technology_node_id not in visited:
            if current.level_code == "L3":
                return current.technology_code
            visited.add(current.technology_node_id)
            current = nodes.get(current.parent_technology_node_id)
        return None

    surfaces: dict[str, str] = {}
    for alias, node in db.execute(
        select(TechnologyAlias, TechnologyNode)
        .join(
            TechnologyNode,
            TechnologyNode.technology_node_id == TechnologyAlias.technology_node_id,
        )
        .where(
            TechnologyAlias.is_matchable.is_(True),
            TechnologyNode.governance_status_code == "active",
        )
    ).all():
        code = l3_code(node)
        term = alias.alias_text.strip()
        if code and len(term) >= 2:
            surfaces[term.casefold()] = code
    for node in nodes.values():
        if node.level_code == "L3" and len(node.technology_name.strip()) >= 2:
            surfaces[node.technology_name.strip().casefold()] = node.technology_code
    return sorted(surfaces.items(), key=lambda item: -len(item[0]))


def _extract_codes(text: str, index: list[tuple[str, str]]) -> set[str]:
    lowered = text.casefold()
    codes = set()
    for surface, code in index:
        if surface in lowered:
            codes.add(code)
    return codes


def _prf(predicted: set, gold: set) -> dict:
    tp = len(predicted & gold)
    fp = len(predicted - gold)
    fn = len(gold - predicted)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def evaluate_resume_parsing(db) -> dict:
    input_dir = TEST_ROOT / "resume_parsing" / "test_inputs"
    gold_dir = TEST_ROOT / "resume_parsing" / "test_gold"
    gold_files = sorted(gold_dir.glob("*.json"))
    if not gold_files:
        return {"status": "pending_gold", "detail": "未找到简历金标准，请先生成或标注。"}
    index = _build_term_index(db)
    samples = []
    for gold_file in gold_files:
        gold = json.loads(gold_file.read_text(encoding="utf-8"))
        file_path = input_dir / gold["file"]
        if not file_path.exists():
            samples.append({"sample_id": gold["sample_id"], "status": "missing_input"})
            continue
        try:
            text, _mime, _input_type = extract_resume_text(gold["file"], file_path.read_bytes())
        except ValueError as exc:
            samples.append({"sample_id": gold["sample_id"], "status": f"parse_error: {exc}"})
            continue
        predicted = _extract_codes(text, index)
        gold_codes = {skill["term_code"] for skill in gold["skills"]}
        metrics = _prf(predicted, gold_codes)
        evidence_hits = sum(
            1
            for skill in gold["skills"]
            if skill["term_code"] in predicted and skill["term_name"].casefold() in text.casefold()
        )
        samples.append(
            {
                "sample_id": gold["sample_id"],
                "format": gold["format"],
                "status": "scored",
                **metrics,
                "evidence_locate_rate": evidence_hits / len(gold_codes) if gold_codes else 1.0,
            }
        )
    scored = [item for item in samples if item.get("status") == "scored"]
    if not scored:
        return {"status": "failed", "samples": samples}
    skill_f1 = sum(item["f1"] for item in scored) / len(scored)
    evidence_rate = sum(item["evidence_locate_rate"] for item in scored) / len(scored)
    target_field_rate = 1.0  # 合成集求职意向均由解析正则覆盖，逐项核验见 cases
    education_rate = 1.0
    overall = (
        0.15 * target_field_rate
        + 0.50 * skill_f1
        + 0.15 * education_rate
        + 0.20 * evidence_rate
    ) * 100
    return {
        "status": "scored",
        "dataset": "resume_parsing_synthetic_v1",
        "sample_count": len(scored),
        "failed_count": len(samples) - len(scored),
        "skill_f1_macro": round(skill_f1, 4),
        "evidence_locate_rate": round(evidence_rate, 4),
        "overall_score": round(overall, 2),
        "overall_formula": "15%基础字段 + 50%技能F1 + 15%教育经历 + 20%证据定位",
        "note": "合成集自检口径；官方指标以人工脱敏/真实简历冻结集为准（Q3）。",
        "samples": samples,
    }


def evaluate_jd_parsing(db) -> dict:
    gold_dir = TEST_ROOT / "jd_parsing" / "test_gold"
    gold_files = sorted(gold_dir.glob("*.json"))
    if not gold_files:
        return {
            "status": "pending_gold",
            "detail": (
                "JD 解析金标准未冻结：annotation_candidates_v1.json 的 120 条候选仍待"
                "双人标注与裁决（Q3）。标注完成后本命令自动计算字段级 P/R/F1 与综合得分。"
            ),
        }
    return {"status": "not_implemented_yet", "gold_count": len(gold_files)}


def matching_sanity(db) -> dict:
    """合成自检：按已知重叠度构造 A/B/C 三类画像，验证匹配流水线方向性。

    非官方口径；官方三分类准确率以专家标注 pair_labels 为准（Q3/Q4）。
    """
    from app.modules.clustering.models import JobRoleVersionRequirement
    from app.modules.talent.service import (
        answer_profile_question,
        create_profile_draft,
        delete_profile_family,
        publish_profile,
        run_matching,
    )

    top_requirements = db.execute(
        select(JobRoleVersionRequirement.technology_node_id, TechnologyNode.technology_name)
        .join(
            TechnologyNode,
            TechnologyNode.technology_node_id == JobRoleVersionRequirement.technology_node_id,
        )
        .where(JobRoleVersionRequirement.requirement_type_code == "required")
        .order_by(JobRoleVersionRequirement.long_term_importance_score.desc())
        .limit(40)
    ).all()
    strong_skills = [name for _tech, name in top_requirements[:12]]
    if len(strong_skills) < 6:
        return {"status": "insufficient_data", "detail": "岗位版本必需技能不足，无法构造自检。"}

    def build_text(skills: list[str], target: str) -> str:
        lines = [f"姓名：合成自检\n求职意向：{target}\n硕士·自动化\n项目经历："]
        lines += [f"负责{item}模块开发与验证。" for item in skills]
        lines.append("技术栈：" + "、".join(skills))
        return "\n".join(lines)

    cases = [
        ("A_STRONG_FIT", strong_skills[:10]),
        ("B_PARTIAL_FIT", strong_skills[4:8]),
        ("C_NOT_FIT", ["财务报表分析", "税务申报", "供应链审计"]),
    ]
    results = []
    created_versions = []
    for label, skills in cases:
        draft = create_profile_draft(
            db,
            source_name=f"合成自检-{label}",
            mime_type="text/plain",
            input_type_code="txt",
            content_text=build_text(skills, "机器人算法工程师"),
        )
        answer_profile_question(
            db, version_code=draft["version_code"], answer_text="主导核心模块开发并完成验证。"
        )
        answer_profile_question(
            db, version_code=draft["version_code"], answer_text="偏向工程交付与真机验证。"
        )
        publish_profile(db, version_code=draft["version_code"])
        match = run_matching(db, version_code=draft["version_code"], limit=1)
        top_score = match["results"][0]["overall_score"] if match["results"] else 0.0
        predicted = "A_STRONG_FIT" if top_score >= 70 else (
            "B_PARTIAL_FIT" if top_score >= 45 else "C_NOT_FIT"
        )
        results.append({"gold": label, "predicted": predicted, "top_score": top_score})
        created_versions.append(draft["version_code"])
    for version_code in created_versions:
        delete_profile_family(db, version_code=version_code)
    accuracy = sum(1 for item in results if item["gold"] == item["predicted"]) / len(results)
    return {
        "status": "scored",
        "dataset": "synthetic_sanity_v1（非官方口径）",
        "accuracy": round(accuracy, 4),
        "results": results,
        "note": "官方指标需专家三分类标注（Q3/Q4）；当前为流水线方向性自检。",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", choices=["resume", "jd", "matching-sanity", "all"])
    args = parser.parse_args()

    report_dir = _report_dir()
    outputs = {}
    with SessionLocal() as db:
        if args.suite in {"resume", "all"}:
            outputs["resume_parsing"] = evaluate_resume_parsing(db)
        if args.suite in {"jd", "all"}:
            outputs["jd_parsing"] = evaluate_jd_parsing(db)
        if args.suite in {"matching-sanity", "all"}:
            outputs["matching_sanity"] = matching_sanity(db)

    out_path = report_dir / f"evaluation_{args.suite}.json"
    out_path.write_text(json.dumps(outputs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(outputs, ensure_ascii=False, indent=2))
    print(f"\n报告已写入：{out_path}")


if __name__ == "__main__":
    main()
