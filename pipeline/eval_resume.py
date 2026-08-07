"""阶段 3 评测：简历技能提取准确率 + 匹配合理性验证。

测试集：阶段 2.5 从 project-export 迁入的 175 份真实简历（resume_skills 为真值）。
- 提取评测：用 extract.py 词典引擎对 raw_text 重新提取，与真值对比 P/R/F1。
  口径说明：真值含大量组合词方向标签（如"工业机器人/人形机器人/家电机器人"，
  源库人才方向级标注，不会字面出现于简历文本），故 Recall 只对"文本内真值"
  （与匹配器同口径判定：整词或组合词≥ 2 个原子真实出现）计算；
  方向级标签单独统计不计入 Recall。Precision 含组合词原子等价命中。
- 匹配评测：对每份有技能的简历跑匹配，统计命中率（Top10 有岗位）与得分分布
用法：python3 -m pipeline.eval_resume [--match-sample 30]
"""
from __future__ import annotations

import argparse

from . import db
from .extract import COMB_SEPARATORS, compile_skills, extract_one, normalize_text


def _atoms(term: str) -> set[str]:
    """技能词 → 归一化原子词集合（组合词拆解，单词保留自身）。"""
    parts = {normalize_text(p) for p in COMB_SEPARATORS.split(term) if len(normalize_text(p)) >= 2}
    parts.add(normalize_text(term))
    return parts


def _atom_patterns(atom: str):
    """原子词 → 与 extract.py 同口径的边界正则（ASCII 词边界保护）。"""
    import re

    if re.search(r"[a-zA-Z0-9_]", atom):
        return re.compile(r"(?<![A-Za-z0-9_])" + re.escape(atom) + r"(?![A-Za-z0-9_])", re.IGNORECASE)
    return re.compile(re.escape(atom), re.IGNORECASE)


def _gold_in_text(term: str, normalized: str) -> bool:
    """真值是否真实出现于文本（与词典匹配器同口径）：
    整词命中，或组合词≥ 2 个原子词按边界规则命中。
    单一泛化原子（如仅"机器人"）不算——那是方向级标签而非文本内容。"""
    atoms = sorted(a for a in _atoms(term) if a)
    whole = _atom_patterns(normalize_text(term)).search(normalized)
    if whole:
        return True
    hit_count = sum(1 for a in atoms if _atom_patterns(a).search(normalized))
    return hit_count >= 2


def eval_extraction(conn) -> dict:
    """提取评测。

    Recall 只对"文本内真值"计算：真值词（或其组合词原子）确实出现于简历文本时，
    衡量正则匹配器是否捕获（这是可提取上限）；文本外的方向级标签单独统计，
    不计入 Recall 分母（字面不存在于文本，任何提取器都无法命中）。
    Precision 照常：预测命中真值（严格或原子等价）/ 全部预测。
    """
    records = compile_skills(conn)
    resumes = conn.execute("SELECT resume_id, raw_text FROM resumes WHERE raw_text IS NOT NULL").fetchall()
    strict_p_hit = atom_eq_p_hit = pred_total = 0
    recall_hit = recall_total = 0
    out_of_text_gold = 0
    resumes_with_gold = 0
    id_to_term = {
        r["skill_id"]: r["skill_term"] for r in conn.execute("SELECT skill_id, skill_term FROM skills")
    }
    for r in resumes:
        gold_ids = {
            row["skill_id"]
            for row in conn.execute(
                "SELECT skill_id FROM resume_skills WHERE resume_id = ?", (r["resume_id"],)
            )
        }
        if not gold_ids:
            continue
        resumes_with_gold += 1
        normalized = normalize_text(r["raw_text"])
        hits = extract_one(r["raw_text"], records)
        pred_ids = {h["skill_id"] for h in hits}
        pred_atoms: set[str] = set()
        for h in hits:
            pred_atoms |= _atoms(id_to_term.get(h["skill_id"], ""))
        pred_total += len(pred_ids)
        strict_p_hit += len(pred_ids & gold_ids)

        for sid in gold_ids:
            term = id_to_term.get(sid, "")
            atoms = _atoms(term)
            # 真值是否出现于文本（与匹配器同口径；仅单一泛化原子的方向标签不算）
            if not _gold_in_text(term, normalized):
                out_of_text_gold += 1
                continue
            recall_total += 1
            if sid in pred_ids or atoms & pred_atoms:
                recall_hit += 1
        # 精确率：预测与真值严格相等或原子等价均算命中
        for h in hits:
            if h["skill_id"] in gold_ids:
                continue  # 已在 strict_p_hit 计入
            if _atoms(id_to_term.get(h["skill_id"], "")) & {
                a for sid in gold_ids for a in _atoms(id_to_term.get(sid, ""))
            }:
                atom_eq_p_hit += 1

    def ratio(num: int, den: int) -> float:
        return num / den if den else 0.0

    precision = ratio(strict_p_hit + atom_eq_p_hit, pred_total)
    recall = ratio(recall_hit, recall_total)
    f1 = ratio(2 * precision * recall, precision + recall) if precision + recall else 0.0
    return {
        "resumes_with_gold": resumes_with_gold,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "in_text_gold": recall_total,
        "in_text_hit": recall_hit,
        "out_of_text_gold": out_of_text_gold,
    }


def eval_matching(conn, sample: int) -> dict:
    from backend.matching import MatchingEngine

    engine = MatchingEngine(conn)
    ids = [
        r["resume_id"]
        for r in conn.execute(
            """
            SELECT rs.resume_id FROM resume_skills rs
            JOIN resumes r ON r.resume_id = rs.resume_id
            WHERE r.raw_text IS NOT NULL
            GROUP BY rs.resume_id LIMIT ?
            """,
            (sample,),
        )
    ]
    hit = 0
    scores: list[float] = []
    for rid in ids:
        result = engine.match(rid, top_n=10)
        if result["matches"]:
            hit += 1
            scores.append(result["matches"][0]["score"])
    scores.sort()
    return {
        "sample": len(ids),
        "match_hit": hit,
        "hit_rate": hit / len(ids) if ids else 0.0,
        "top1_score_median": scores[len(scores) // 2] if scores else 0.0,
        "top1_score_max": max(scores) if scores else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="阶段 3 评测：简历提取 P/R + 匹配合理性")
    parser.add_argument("--match-sample", type=int, default=30, help="匹配评测抽样份数")
    args = parser.parse_args()

    conn = db.connect()
    print("=== 简历技能提取评测（真值=迁入的 resume_skills）===")
    ext = eval_extraction(conn)
    print(f"  有真值简历: {ext['resumes_with_gold']} 份")
    print(f"  Precision={ext['precision']:.3f}（预测命中真值/全部预测，含组合词原子等价）")
    print(f"  文本内真值 Recall={ext['recall']:.3f}（{ext['in_text_hit']}/{ext['in_text_gold']}）")
    print(f"  F1={ext['f1']:.3f}；文本外方向级标签 {ext['out_of_text_gold']} 条（不计入 Recall，字面不存在于简历文本）")

    print(f"=== 匹配合理性评测（抽样 {args.match_sample} 份）===")
    mt = eval_matching(conn, args.match_sample)
    print(f"  Top10 命中岗位: {mt['match_hit']}/{mt['sample']}（{mt['hit_rate']:.1%}）")
    print(f"  Top1 得分中位数 {mt['top1_score_median']:.3f}，最高 {mt['top1_score_max']:.3f}")
    conn.close()


if __name__ == "__main__":
    main()
