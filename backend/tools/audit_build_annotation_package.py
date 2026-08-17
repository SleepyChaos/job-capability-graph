"""窗口 A-1 子任务 1.3a:组装 JD 抽取质量人工标注包。

输入:
1. `build_jd_annotation_batch.py` 在 backend 容器内生成的候选清单(100 份,
   T1–T7 分层 + review 优先补足;生成命令见 docs/reports/annotation_package/标注说明.md)
2. .audit-data/ 快照(04 语料正文、01 命中明细、06 词表节点、07 job_code 映射)

输出(docs/reports/annotation_package/):
- jd_annotation_batch_001.json:每份样本含 JD 正文、当前抽取结果(冻结快照)、
  待人工填写的 expected_l3_codes / role_type / annotator_notes 字段
- l3_reference.json:全部 L3 技术点代码与名称(标注参照)

本脚本只读,不修改任何业务数据;确定性排序,重跑得到逐字节相同的输出。

用法:
    python backend/tools/audit_build_annotation_package.py \
        --candidates .audit-data/jd_annotation_candidates.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from audit_tsv import iter_mysql_tsv

CORPUS_COLS = [
    "job_posting_id",
    "job_title_normalized",
    "job_title_raw",
    "job_level_code",
    "region_text",
    "parse_status_code",
    "parse_quality_score",
    "accepted_cnt",
    "review_cnt",
    "distinct_node_cnt",
    "jd_clean_text",
]
HITS_COLS = [
    "assessment_id",
    "job_posting_id",
    "requirement_id",
    "status",
    "reason_code",
    "score",
    "feature_weight",
    "ambiguity_rule_id",
    "raw_term",
    "mention_count",
    "mapping_method_code",
    "req_node_code",
    "req_node_name",
    "span_text",
    "alias_id",
    "alias_text",
    "normalized_alias",
    "is_matchable",
    "alias_type_code",
    "alias_node_code",
    "alias_node_name",
    "alias_l3_code",
    "alias_l3_name",
]
NODES_COLS = [
    "technology_node_id",
    "technology_code",
    "level_code",
    "technology_name",
    "parent_code",
    "parent_name",
    "parent_level",
]

ROLE_TYPE_GUIDE = {
    "embodied_algo": "具身算法岗(感知/规划/控制/学习/VLA 等算法研发)",
    "hardware": "硬件岗(整机/结构/电控/传感器/驱动等硬件研发)",
    "engineering": "工程岗(部署/测试/数据/平台/嵌入式等工程实现)",
    "non_technical": "非技术岗(销售/产品/运营/职能等)",
}


def build_extraction(hits: list[dict]) -> list[dict]:
    """按 (L3, 状态) 去重汇总当前抽取,保持确定性顺序。"""
    seen: dict[tuple[str, str], dict] = {}
    for row in sorted(hits, key=lambda r: int(r["assessment_id"])):
        key = (row["req_node_code"], row["status"])
        if key not in seen:
            seen[key] = {
                "technology_code": row["req_node_code"],
                "technology_name": row["req_node_name"],
                "status": row["status"],
                "matched_terms": [],
            }
        term = row["normalized_alias"]
        if term not in seen[key]["matched_terms"]:
            seen[key]["matched_terms"].append(term)
    return list(seen.values())


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidates",
        type=Path,
        default=repo_root / ".audit-data" / "jd_annotation_candidates.json",
    )
    parser.add_argument("--data-dir", type=Path, default=repo_root / ".audit-data")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=repo_root / "docs" / "reports" / "annotation_package",
    )
    parser.add_argument("--batch-id", default="jd_annotation_batch_001")
    args = parser.parse_args()

    candidates = json.loads(args.candidates.read_text(encoding="utf-8"))

    corpus_by_id: dict[int, dict] = {}
    for row in iter_mysql_tsv((args.data_dir / "04_jd_corpus.tsv").read_text("utf-8"), CORPUS_COLS):
        corpus_by_id[int(row["job_posting_id"])] = row

    id_by_code: dict[str, int] = {}
    for row in iter_mysql_tsv(
        (args.data_dir / "07_job_code_map.tsv").read_text("utf-8"),
        ["job_code", "job_posting_id"],
    ):
        id_by_code[row["job_code"]] = int(row["job_posting_id"])

    hits_by_posting: dict[int, list[dict]] = defaultdict(list)
    for row in iter_mysql_tsv((args.data_dir / "01_alias_hits.tsv").read_text("utf-8"), HITS_COLS):
        hits_by_posting[int(row["job_posting_id"])].append(row)

    nodes = [
        row
        for row in iter_mysql_tsv(
            (args.data_dir / "06_taxonomy_nodes.tsv").read_text("utf-8"), NODES_COLS
        )
        if row["level_code"] == "L3"
    ]

    samples = []
    for item in candidates["samples"]:
        code = item["job_code"]
        posting_id = id_by_code.get(code)
        if posting_id is None:
            raise SystemExit(f"候选 {code} 在 07_job_code_map 中缺失")
        corpus_row = corpus_by_id.get(posting_id)
        if corpus_row is None:
            raise SystemExit(f"候选 {code}(posting {posting_id})不在 run 3 语料内")
        samples.append(
            {
                "sample_id": item["sample_id"],
                "job_code": code,
                "job_title": corpus_row["job_title_normalized"],
                "primary_domain": item["primary_domain"],
                "parse_quality_score": item["parse_quality_score"],
                "accepted_cnt": int(corpus_row["accepted_cnt"]),
                "review_cnt": int(corpus_row["review_cnt"]),
                "jd_text": corpus_row["jd_clean_text"],
                "current_extraction": build_extraction(hits_by_posting.get(posting_id, [])),
                # ---- 以下字段由人工标注填写 ----
                "expected_l3_codes": [],
                "role_type": None,
                "annotator_notes": "",
                "annotation_status": "pending",
            }
        )

    package = {
        "batch_id": args.batch_id,
        "dataset_id": candidates["dataset_id"],
        "purpose": (
            "任务组 1.3 人工标注:expected_l3_codes = 标注者认定该 JD 应抽出的 L3 技术点代码列表"
        ),
        "parse_run_code": candidates["parse_run_code"],
        "input_snapshot_hash": candidates["input_snapshot_hash"],
        "selection_method": candidates["selection_method"],
        "domain_distribution": candidates["domain_distribution"],
        "caliber_note": (
            "current_extraction 为 run jdparse_e7328e6370fbee62e79d2098 的冻结快照"
            "(含 accepted 与 needs_review 及命中词);评估默认只对照 accepted"
        ),
        "role_type_options": ROLE_TYPE_GUIDE,
        "warning": candidates["warning"],
        "samples": samples,
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{args.batch_id}.json"
    out_path.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    l3_ref = {
        "taxonomy_version": "v1.1",
        "count": len(nodes),
        "nodes": [
            {"code": n["technology_code"], "name": n["technology_name"]}
            for n in sorted(nodes, key=lambda n: n["technology_code"])
        ],
    }
    (args.out_dir / "l3_reference.json").write_text(
        json.dumps(l3_ref, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with_ev = sum(1 for s in samples if s["accepted_cnt"] > 0)
    zero_ev = len(samples) - with_ev
    print(f"{out_path}: {len(samples)} 份样本(有 accepted 证据 {with_ev} / 零 {zero_ev})")
    print(f"L3 参照 {len(nodes)} 个节点")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
