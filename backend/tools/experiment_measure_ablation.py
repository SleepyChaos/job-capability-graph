"""E3 / E4：两处设计决策的机械性消融。

两项主张此前只有解析论证，本工具把它们变成可复核的事实。

**E3　覆盖率度量：非对称覆盖率 vs 对称 Jaccard**

文档 4.1.2 主张「非对称覆盖率优于 Jaccard，因为 Jaccard 会因岗位技术词更多而
系统性压低覆盖率，把已被覆盖的候选误判为新岗位」。这一主张可以被直接检验：
逐个候选比较两种度量下的分类结果，统计「候选完全落在某岗位能力集内、
却在 Jaccard 下被判为 potential_new_role」的案例数。

预注册判据：若该类案例数为 0，则本主张在当前数据上无实证支持。

**E4　分档门控：合取门控 vs 单一评分阈值**

文档 7.1 贡献二主张「合取门控抗特定偏差——单一企业的一次特殊招聘无法凭高分升档」。
检验方式：用评分阈值重新分档，统计带有单一企业/单一来源风险旗标的候选中，
有多少会被升到 emerging 档。

预注册判据：合取门控下应为 0；若评分阈值下 > 0，主张得到机械性证实。
这证明门控确实挡住了某类候选，**不证明被挡住的候选一定不该升档**。

用法（backend 目录 / 容器内）：
    python -m tools.experiment_measure_ablation --target-date 2026-08-31
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.modules.discovery.models import CandidateTechnology, EmergingRoleCandidate
from app.modules.discovery.service import DEFAULT_PARAMETERS, _role_capability_profiles
from app.modules.taxonomy.models import TechnologyNode

EXPERIMENT_VERSION = "measure_ablation_v1"

# 与线上 classification 相同的两个阈值。
EXISTING_ROLE_THRESHOLD = 0.75
ROLE_EVOLUTION_THRESHOLD = 0.45
# emerging 档的评分门槛，用于 E4 的「单一评分阈值」对照。
EMERGING_SCORE_THRESHOLD = 65.0
# 表示「单一来源偏差」的风险旗标。
BIAS_FLAGS = ("single_company_signal", "single_source_signal")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="覆盖率度量与分档门控的机械性消融。")
    parser.add_argument("--target-date", type=date.fromisoformat, required=True)
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    return parser.parse_args()


def classify(overlap: float) -> str:
    if overlap >= EXISTING_ROLE_THRESHOLD:
        return "existing_role"
    if overlap >= ROLE_EVOLUTION_THRESHOLD:
        return "role_evolution"
    return "potential_new_role"


def load_candidate_technologies(db: Session) -> dict[int, frozenset[str]]:
    """候选 → 技术编码集合。用编码而非节点 id，跨词表版本才可比。"""
    rows = db.execute(
        select(CandidateTechnology.emerging_role_candidate_id, TechnologyNode.technology_code)
        .join(
            TechnologyNode,
            TechnologyNode.technology_node_id == CandidateTechnology.technology_node_id,
        )
    ).all()
    grouped: dict[int, set[str]] = {}
    for candidate_id, code in rows:
        grouped.setdefault(candidate_id, set()).add(code)
    return {candidate_id: frozenset(codes) for candidate_id, codes in grouped.items()}


def coverage_ablation(db: Session, target_date: date) -> dict:
    """E3：对每个候选，比较非对称覆盖率与对称 Jaccard 的分类结果。"""
    profiles = _role_capability_profiles(
        db,
        target_date,
        min_technology_count=int(DEFAULT_PARAMETERS["min_role_technology_count"]),
    )
    technologies = load_candidate_technologies(db)
    candidates = list(db.scalars(select(EmergingRoleCandidate)))

    asymmetric_counts: Counter[str] = Counter()
    jaccard_counts: Counter[str] = Counter()
    downgraded: list[dict] = []

    for candidate in candidates:
        target = technologies.get(candidate.emerging_role_candidate_id, frozenset())
        if not target:
            continue
        best_asym = 0.0
        best_jac = 0.0
        best_role_tech: frozenset[str] = frozenset()
        for _role_id, role_tech in profiles:
            shared = len(target & role_tech)
            asym = shared / len(target)
            union = len(target | role_tech)
            jac = shared / union if union else 0.0
            if asym > best_asym:
                best_asym = asym
                best_role_tech = role_tech
            best_jac = max(best_jac, jac)

        asym_class = classify(best_asym)
        jac_class = classify(best_jac)
        asymmetric_counts[asym_class] += 1
        jaccard_counts[jac_class] += 1

        # 主张要检验的正是这一类：候选完全（或高度）落在某岗位能力集内，
        # 非对称覆盖率认定已被覆盖，而 Jaccard 因岗位技术词更多把它判成新岗位。
        if asym_class == "existing_role" and jac_class == "potential_new_role":
            downgraded.append({
                "candidate_code": candidate.candidate_code,
                "proposed_name": candidate.proposed_name,
                "candidate_technology_count": len(target),
                "nearest_role_technology_count": len(best_role_tech),
                "asymmetric_coverage": round(best_asym, 3),
                "jaccard": round(best_jac, 3),
            })

    return {
        "candidate_count": len(technologies),
        "asymmetric_distribution": dict(asymmetric_counts),
        "jaccard_distribution": dict(jaccard_counts),
        "misclassified_as_new_under_jaccard": len(downgraded),
        "examples": sorted(downgraded, key=lambda item: -item["asymmetric_coverage"])[:8],
    }


def gate_ablation(db: Session) -> dict:
    """E4：用评分阈值替代合取门控重新分档，统计有偏差旗标的候选会不会被升档。"""
    candidates = list(db.scalars(select(EmergingRoleCandidate)))
    gate_emerging = 0
    score_emerging = 0
    biased_under_gate = 0
    biased_under_score: list[dict] = []

    for candidate in candidates:
        flags = set(candidate.risk_flags_json or [])
        has_bias = bool(flags & set(BIAS_FLAGS))
        score = float(candidate.candidate_score)

        if candidate.maturity_stage_code == "emerging":
            gate_emerging += 1
            if has_bias:
                biased_under_gate += 1
        if score >= EMERGING_SCORE_THRESHOLD:
            score_emerging += 1
            if has_bias:
                biased_under_score.append({
                    "candidate_code": candidate.candidate_code,
                    "proposed_name": candidate.proposed_name,
                    "score": round(score, 1),
                    "stage_under_gate": candidate.maturity_stage_code,
                    "risk_flags": sorted(flags & set(BIAS_FLAGS)),
                })

    return {
        "candidate_count": len(candidates),
        "emerging_under_conjunctive_gate": gate_emerging,
        "emerging_under_score_threshold": score_emerging,
        "biased_emerging_under_gate": biased_under_gate,
        "biased_emerging_under_score": len(biased_under_score),
        "score_threshold": EMERGING_SCORE_THRESHOLD,
        "examples": sorted(biased_under_score, key=lambda item: -item["score"])[:8],
    }


def render(coverage: dict, gate: dict, args: argparse.Namespace) -> None:
    print(f"# 度量与门控消融（{EXPERIMENT_VERSION}）\n")
    print(f"- 目标日期：{args.target_date} · 候选总数：{coverage['candidate_count']}\n")

    print("## E3　覆盖率度量：非对称覆盖率 vs 对称 Jaccard\n")
    print("| 分类 | 非对称覆盖率 | 对称 Jaccard |")
    print("| --- | ---: | ---: |")
    for key, label in (
        ("existing_role", "既有岗位"),
        ("role_evolution", "岗位演化"),
        ("potential_new_role", "潜在新岗位"),
    ):
        print(
            f"| {label} | {coverage['asymmetric_distribution'].get(key, 0)} "
            f"| {coverage['jaccard_distribution'].get(key, 0)} |"
        )
    count = coverage["misclassified_as_new_under_jaccard"]
    print(f"\n**被 Jaccard 误判为潜在新岗位的候选：{count} 个**")
    if count:
        print(
            "\n（非对称覆盖率判定为「已被既有岗位覆盖」，"
            "Jaccard 因岗位技术词更多而判成新岗位）\n"
        )
        print("| 候选 | 候选技术数 | 最近岗位技术数 | 非对称覆盖率 | Jaccard |")
        print("| --- | ---: | ---: | ---: | ---: |")
        for item in coverage["examples"]:
            print(
                f"| {item['proposed_name']} | {item['candidate_technology_count']} "
                f"| {item['nearest_role_technology_count']} | {item['asymmetric_coverage']} "
                f"| {item['jaccard']} |"
            )
    else:
        print("\n> 该类案例为 0——「非对称覆盖率优于 Jaccard」这一主张在当前数据上**无实证支持**，")
        print("> 文档应改为只陈述解析理由，不宣称实测优势。")

    print(f"\n## E4　分档门控：合取门控 vs 评分阈值（≥{gate['score_threshold']}）\n")
    print("| 项 | 合取门控 | 评分阈值 |")
    print("| --- | ---: | ---: |")
    print(f"| 升到 emerging 的候选 | {gate['emerging_under_conjunctive_gate']} "
          f"| {gate['emerging_under_score_threshold']} |")
    print(f"| 其中带单一企业/单一来源旗标 | **{gate['biased_emerging_under_gate']}** "
          f"| **{gate['biased_emerging_under_score']}** |")
    if gate["biased_emerging_under_score"] > gate["biased_emerging_under_gate"]:
        print("\n> 合取门控确实挡住了带偏差旗标的候选，主张得到机械性证实。")
        print("> 注意这只证明门控挡住了某类候选，**不证明被挡住的候选一定不该升档**。\n")
        print("| 候选 | 评分 | 合取门控下的档位 | 风险旗标 |")
        print("| --- | ---: | --- | --- |")
        for item in gate["examples"]:
            print(
                f"| {item['proposed_name']} | {item['score']} | {item['stage_under_gate']} "
                f"| {' · '.join(item['risk_flags'])} |"
            )
    else:
        print("\n> 两种机制下带偏差旗标的候选数相同——当前数据里不存在该情形，")
        print("> 「抗特定偏差」这一主张缺乏实证支持，文档应弱化。")


def main() -> None:
    args = parse_args()
    with SessionLocal() as session:
        coverage = coverage_ablation(session, args.target_date)
        gate = gate_ablation(session)
    if args.format == "json":
        print(json.dumps({"coverage": coverage, "gate": gate}, ensure_ascii=False))
        return
    render(coverage, gate, args)


if __name__ == "__main__":
    main()
