"""技术词提取：词典正则提取（移植自项目二 extract_tech_keywords.py）。

改造点：
1. 词典来源改为统一库 skills 表（不再读 Excel 硬编码路径）
2. 结果直接写 job_skills（带证据片段 evidence 与置信度 confidence）
3. 去掉 Coze/多进程依赖；数据规模（千级 JD）单进程足够快
"""
from __future__ import annotations

import argparse
import re
import sqlite3
from typing import List, Tuple

from . import db
# 阶段 4 审核策略（与 backend/review.py 同源，避免重复定义门限）
from backend.review import decide_status as _review_decide_status

COMB_SEPARATORS = re.compile(r"[/,，;；+、\\|]")
PAREN_PATTERN = re.compile(r"[（(].*?[）)]")
EVIDENCE_WINDOW = 40  # 证据片段取命中位置前后各 N 字符

METRIC_SUFFIXES = [
    "m", "mm", "cm", "km", "um", "nm", "inch",
    "g", "kg", "mg", "t", "lb",
    "ms", "us", "ns", "min", "h", "hz", "khz", "mhz", "ghz",
    "pa", "kpa", "mpa", "bar", "psi",
    "n", "kn", "j", "kj", "w", "kw", "mw",
    "v", "kv", "a", "ma", "ah",
    "deg", "rad", "%", "ppm",
    "m/s", "km/h", "rpm",
    "lux", "k", "lm", "db", "dbm",
]


def normalize_text(text: str) -> str:
    """移植自项目二：全角转半角、去特殊字符、小写化。"""
    if text is None:
        return ""
    text = str(text)
    text = text.translate(
        str.maketrans("，。！？；：“”‘’（）【】、", ",.!?;:\"\"''()[] ")
    )
    text = re.sub(r"[\s\-/\\|]+", " ", text)
    text = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9_\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def _single_pattern(clean_term: str):
    if not clean_term:
        return None
    if re.search(r"[a-zA-Z0-9_]", clean_term):
        # ASCII 边界：中文字符不视为单词字符（否则 "PyTorch框架" 无法命中）
        return re.compile(r"(?<![A-Za-z0-9_])" + re.escape(clean_term) + r"(?![A-Za-z0-9_])", re.IGNORECASE)
    return re.compile(re.escape(clean_term), re.IGNORECASE)


def covered_by_longer(span: Tuple[int, int], spans: List[Tuple[int, int]]) -> bool:
    """子串抑制：候选命中区间若完全包含在已命中长词区间内，不单独计入。"""
    s, e = span
    return any(s2 <= s and e <= e2 and (s2, e2) != (s, e) for s2, e2 in spans)


def build_term_pattern(term: str, l4_type: str) -> Tuple[re.Pattern | None, List[re.Pattern]]:
    clean = normalize_text(term)
    sub_patterns: List[re.Pattern] = []
    if l4_type == "组合词":
        for atom in COMB_SEPARATORS.split(term):
            atom_clean = normalize_text(atom)
            if len(atom_clean) >= 2:
                pat = _single_pattern(atom_clean)
                if pat:
                    sub_patterns.append(pat)
    return _single_pattern(clean), sub_patterns


def build_metric_patterns(clean_term: str) -> List[re.Pattern]:
    patterns = []
    for suffix in METRIC_SUFFIXES:
        if suffix in clean_term:
            patterns.append(re.compile(r"\d+(?:\.\d+)?\s*" + re.escape(suffix), re.IGNORECASE))
    return patterns


def compile_skills(conn: sqlite3.Connection) -> list[dict]:
    """从统一本体加载技能词并预编译正则。"""
    records = []
    for skill in db.load_skills(conn):
        term = skill["skill_term"]
        l4_type = skill["l4_type"] or "细分词"
        main, subs = build_term_pattern(term, l4_type)
        if main is None:
            continue
        records.append(
            {
                "skill_id": skill["skill_id"],
                "term": term,
                "clean": normalize_text(term),
                "l4_type": l4_type,
                "l1_code": skill["l1_code"],
                "pattern": main,
                "sub_patterns": subs,
                "metric_patterns": build_metric_patterns(normalize_text(term))
                if l4_type == "指标词"
                else [],
            }
        )
    # 长词优先，避免短词抢占（与项目二一致的排序策略）
    records.sort(key=lambda r: len(r["clean"]), reverse=True)
    return records


def locate_evidence(normalized: str, match: re.Match) -> str:
    """证据溯源：命中位置前后各取 EVIDENCE_WINDOW 字符作为 JD 原文片段。"""
    start = max(0, match.start() - EVIDENCE_WINDOW)
    end = min(len(normalized), match.end() + EVIDENCE_WINDOW)
    return normalized[start:end].strip()


def _subterm_hits(
    span_text: str, normalized: str, span_start: int, records: list[dict], matched: set[str]
) -> list[dict]:
    """子词回溯：在长词命中区间内再匹配更短的本体词（如"深度强化学习"→"强化学习"、
    "灵巧抓取VLA"→"灵巧抓取"）。长词优先排序保证短词仅从已命中的长词区间内回溯，
    不会引入文本其他位置的偶然子串噪声。"""
    sub_results: list[dict] = []
    for rec in records:
        if rec["clean"] in matched:
            continue
        if rec["clean"] not in span_text:
            continue
        m = rec["pattern"].search(span_text)
        if not m:
            continue
        matched.add(rec["clean"])
        abs_start = span_start + m.start()
        abs_end = span_start + m.end()
        # 证据：以绝对偏移在全文上取前后窗口
        ev_start = max(0, abs_start - EVIDENCE_WINDOW)
        ev_end = min(len(normalized), abs_end + EVIDENCE_WINDOW)
        sub_results.append(
            {
                "skill_id": rec["skill_id"],
                "evidence": normalized[ev_start:ev_end].strip(),
                "l4_type": rec["l4_type"],
                "_span": (abs_start, abs_end),
            }
        )
    return sub_results


def extract_one(jd_text: str, records: list[dict]) -> list[dict]:
    """对单条文本做词典匹配，返回 [{skill_id, evidence, l4_type}, ...]。

    含子词回溯：长词命中后，区间内出现更短的本体词（"深度强化学习"→"强化学习"）
    一并计入，提升简历类短文本的技能召回。"""
    normalized = normalize_text(jd_text)
    no_paren = PAREN_PATTERN.sub(" ", normalized)
    if not normalized:
        return []

    matched: set[str] = set()
    matched_spans: List[Tuple[int, int]] = []
    results: list[dict] = []
    pending_spans: List[Tuple[int, int]] = []  # 待子词回溯的命中区间
    for rec in records:
        if rec["clean"] in matched:
            continue
        evidence = None
        span: Tuple[int, int] | None = None
        m = rec["pattern"].search(no_paren) or rec["pattern"].search(normalized)
        if m:
            evidence = locate_evidence(normalized, m)
            span = (m.start(), m.end())
        elif rec["sub_patterns"]:
            for sub in rec["sub_patterns"]:
                m = sub.search(no_paren) or sub.search(normalized)
                if m:
                    evidence = locate_evidence(normalized, m)
                    span = (m.start(), m.end())
                    break
        elif rec["metric_patterns"]:
            for metric in rec["metric_patterns"]:
                m = metric.search(no_paren) or metric.search(normalized)
                if m:
                    evidence = locate_evidence(normalized, m)
                    span = (m.start(), m.end())
                    break
        if evidence is not None:
            if span is not None and covered_by_longer(span, matched_spans):
                continue
            matched.add(rec["clean"])
            if span is not None:
                matched_spans.append(span)
                pending_spans.append(span)
            results.append(
                {"skill_id": rec["skill_id"], "evidence": evidence, "l4_type": rec["l4_type"]}
            )

    # 子词回溯：长词命中区间内补发更短的本体词（records 已按长度降序，短词在后）
    for s, e in pending_spans:
        span_text = normalized[s:e]
        for sub in _subterm_hits(span_text, normalized, s, records, matched):
            span = sub.pop("_span")
            matched_spans.append(span)
            results.append(sub)
    return results


def run_extraction(
    conn: sqlite3.Connection, reextract: bool = False, l1_filter: str | None = None
) -> dict:
    records = compile_skills(conn)
    if l1_filter:
        codes = {c.strip() for c in l1_filter.split(",") if c.strip()}
        records = [r for r in records if r["l1_code"] in codes]
        print(f"词典域过滤: {sorted(codes)}")
    print(f"本体技能词（可匹配）: {len(records)} 条")

    jobs = conn.execute("SELECT job_id, jd_text FROM jobs").fetchall()
    if not reextract:
        done = {
            r["job_id"]
            for r in conn.execute("SELECT DISTINCT job_id FROM job_skills").fetchall()
        }
        jobs = [j for j in jobs if j["job_id"] not in done]
    print(f"待提取岗位: {len(jobs)} 条")

    total_edges = 0
    jobs_with_hits = 0
    for i, job in enumerate(jobs):
        hits = extract_one(job["jd_text"], records)
        if hits:
            jobs_with_hits += 1
        for h in hits:
            # 阶段 4 审核状态机：词典命中且置信度达标且有证据 → 自动放行，否则待审
            status = _review_decide_status(
                "dictionary", 0.95, has_evidence=bool(h.get("evidence"))
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO job_skills
                (job_id, skill_id, evidence, confidence, l4_type, source, review_status)
                VALUES (?, ?, ?, 0.95, ?, 'dictionary', ?)
                """,
                (job["job_id"], h["skill_id"], h["evidence"], h["l4_type"], status),
            )
        total_edges += len(hits)
        if (i + 1) % 200 == 0:
            print(f"  已处理 {i + 1}/{len(jobs)}")
    conn.commit()

    edge_count = conn.execute("SELECT COUNT(*) AS c FROM job_skills").fetchone()["c"]
    stats = {"processed": len(jobs), "jobs_with_hits": jobs_with_hits, "new_edges": total_edges, "total_edges": edge_count}
    print(f"提取完成：处理 {stats['processed']} 岗位，命中 {stats['jobs_with_hits']}，"
          f"新增边 {stats['new_edges']}，job_skills 总量 {stats['total_edges']}")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="词典正则提取 JD 技术词写入 job_skills")
    parser.add_argument("--reextract", action="store_true", help="全量重跑（默认增量）")
    parser.add_argument("--l1", default=None, help="限定词典 L1 域（逗号分隔，如 AI,BD,IOT,IS）")
    args = parser.parse_args()
    conn = db.connect()
    db.init_db(conn)
    run_extraction(conn, reextract=args.reextract, l1_filter=args.l1)
    conn.close()


if __name__ == "__main__":
    main()
