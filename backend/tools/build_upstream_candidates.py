"""S4：把缺口技术对扩展成能力组合，生成新岗位候选。

**与自动推演的候选性质不同，因此单独成一类。** 自动推演的候选来自 JD 语料内部的
频繁技术组合，回答「这个组合在我们的岗位库里有没有对应」；本工具的候选来自
**上游语料（论文 + 专利）中已成形、而 JD 中从未出现**的技术组合，回答「研究侧已经
在一起做的事，招聘侧还没有」。两者混在一个池子里会让人分不清哪个是哪个，所以
用独立的推演模式 `upstream_gap` 与独立的分类 `upstream_signal` 落库。

**只收 A/B 级。** C 级（至少一侧技术在 JD 中从未出现）与「语料域偏离」在本系统内
无法区分，不进候选池——详见《17》S3 小节。

**C 级另按技术点聚合成待核查清单，写入推演运行的结果摘要。** 判断单位取技术点而非
技术对：96 对背后只有几十个技术，而每一对要问的其实是同一个问题——「这个技术属不属于
具身智能招聘范围」。按技术点聚合后，审阅者做几十次判断而不是上百次，且每次判断可以
复用到该技术涉及的所有对上。清单写进 `result_summary_json` 而不是另建表，
这样审核台从数据库读即可，API 不必去读语料文件。

**技术对如何扩成组合。** 把 A/B 级的缺口对看成一张图，找其中的**团**（clique）：
团内任意两个技术之间都是缺口对，因此整个组合在 JD 中必然从未同时出现。这比
「随便把共享一个技术的对拼起来」严格——后者只保证部分对是缺口，整体未必是。
团的大小上限取 4，与自动推演的闭项集口径一致。

**候选评分不复用自动推演那套。** 那套评分的输入是 JD 侧的支撑量（企业数、来源数、
观测窗），而本类候选在 JD 侧恰恰为零，套用会得到一律接近 0 的分数、失去区分度。

评分由三项相乘：

- **上游证据强度**——组合内各对的最小共现次数（木桶原理：组合成立与否取决于最弱
  的那一环），取对数压缩。**不能直接用次数**：`深度学习 + 分割与实例感知` 共现 56 次
  却只是个泛化组合，线性计分会让它压过所有真正有意思的组合。
- **时近性**——组合在研究侧站住脚的时间距今越近，越可能是尚未传导到招聘的新组合；
  站住脚在 2019 年而至今未进招聘的，更可能是它根本不形成岗位。按年衰减。
- **等级系数**——A 级的缺口在统计上更可信。

结果是「小而新」的组合排在「大而泛」的前面，这与本工具的用途一致。

用法（backend 目录 / 容器内）：
    python -m tools.build_upstream_candidates --extracted /srv/data/upstream/combined --dry-run
    python -m tools.build_upstream_candidates --extracted /srv/data/upstream/combined --execute
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.db.session import SessionLocal
from app.infrastructure.llm import generate, llm_available
from app.modules.clustering.models import JobClusteringRun
from app.modules.data_center.models import ReviewTask
from app.modules.discovery.algorithm import estimate_transmission_lag
from app.modules.discovery.models import (
    CandidateTechnology,
    DiscoveryRun,
    EmergingRoleCandidate,
)
from app.modules.discovery.service import candidate_snapshot
from app.modules.taxonomy.models import TechnologyNode, TechnologyTaxonomyVersion

MODE_CODE = "upstream_gap"
CLASSIFICATION = "upstream_signal"
ALGORITHM_VERSION = "upstream_gap_candidate_v1"
PROMPT_VERSION = "upstream_gap_naming_v1"
MAX_COMBINATION_SIZE = 4
# 等级系数：A 级的缺口在统计上更可信，同等上游证据下给更高的分。
GRADE_WEIGHT = {"A": 1.0, "B": 0.7}
# 时近性的年衰减：站住脚每早一年，权重乘一次这个系数。
RECENCY_DECAY_PER_YEAR = 0.55


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="由缺口技术对生成新岗位候选。")
    parser.add_argument("--extracted", type=Path, required=True)
    parser.add_argument("--min-cooccurrence", type=int, default=3)
    parser.add_argument("--grades", default="A,B", help="纳入候选池的等级")
    parser.add_argument(
        "--limit", type=int, default=40, help="B 级候选的名额上限；A 级不受限，全部保留"
    )
    parser.add_argument("--execute", action="store_true", help="真正落库（默认只预览）")
    return parser.parse_args()


def load_pairs(args: argparse.Namespace) -> list[dict]:
    """复用 find_upstream_only_pairs 的分级判据，不另起一套。

    直接调用它的内部函数而不是拼 argv 再解析——判据只有一处实现，
    两边的等级定义永远一致。
    """
    from tools import find_upstream_only_pairs as gap

    up_dates = gap.load_upstream(args.extracted)
    by_job, mentions = gap.load_jd()
    total_jobs = len(by_job)
    from itertools import combinations as _combos

    jd_pairs = {p for codes in by_job.values() for p in _combos(sorted(codes), 2)}
    wanted = {g.strip().upper() for g in args.grades.split(",") if g.strip()}

    items = []
    for pair, days in up_dates.items():
        if len(days) < args.min_cooccurrence:
            continue
        left, right = pair
        if pair in jd_pairs:
            continue
        if left.rsplit(".", 1)[0] == right.rsplit(".", 1)[0]:
            continue
        expected = mentions[left] * mentions[right] / total_jobs if total_jobs else 0
        if mentions[left] == 0 or mentions[right] == 0:
            grade = "C"
        elif expected >= 2.0:
            grade = "A"
        else:
            grade = "B"
        if grade not in wanted:
            continue
        items.append({
            "grade": grade,
            "pair": [left, right],
            "names": [left, right],
            "upstream_cooccurrence": len(days),
            "established_month": days[args.min_cooccurrence - 1][:7],
            "jd_mentions": [mentions[left], mentions[right]],
        })
    return items


def find_cliques(pairs: list[dict]) -> list[dict]:
    """在缺口对构成的图上找团。

    团内任意两个技术之间都是缺口对，因此整个组合在 JD 中必然从未同时出现——
    这是「组合级缺口」的严格定义。只把共享一个技术的对拼起来是不够的：
    那样得到的集合里可能存在某两个技术其实经常一起出现。
    """
    edge: dict[frozenset[str], dict] = {}
    neighbours: dict[str, set[str]] = defaultdict(set)
    for item in pairs:
        left, right = item["pair"]
        edge[frozenset((left, right))] = item
        neighbours[left].add(right)
        neighbours[right].add(left)

    found: dict[frozenset[str], dict] = {}
    for key, item in edge.items():
        found[key] = {"members": key, "edges": [item]}

    # 逐步扩张：把每个已知团尝试加入一个与团内所有成员都相连的技术。
    frontier = list(found.values())
    while frontier:
        grown: list[dict] = []
        for clique in frontier:
            members = clique["members"]
            if len(members) >= MAX_COMBINATION_SIZE:
                continue
            shared = set.intersection(*(neighbours[m] for m in members))
            for extra in shared - members:
                key = members | {extra}
                if key in found:
                    continue
                edges = clique["edges"] + [
                    edge[frozenset((extra, m))] for m in members
                ]
                found[key] = {"members": key, "edges": edges}
                grown.append(found[key])
        if not grown:
            break
        frontier = grown

    results = []
    for key, clique in found.items():
        edges = clique["edges"]
        # 木桶原理：组合能否成立取决于证据最弱的那一环。
        weakest = min(item["upstream_cooccurrence"] for item in edges)
        grade = "A" if all(item["grade"] == "A" for item in edges) else "B"
        established = max(item["established_month"] for item in edges)
        age_years = max(0.0, (date.today() - _month_start(established)).days / 365.25)
        score = (
            math.log1p(weakest)
            * (RECENCY_DECAY_PER_YEAR**age_years)
            * GRADE_WEIGHT[grade]
        )
        results.append({
            "technology_codes": sorted(key),
            "edges": edges,
            "min_cooccurrence": weakest,
            "grade": grade,
            "established_month": established,
            "age_years": round(age_years, 1),
            "score": round(score, 3),
        })
    results.sort(key=lambda item: -item["score"])
    return results


def apply_limit(cliques: list[dict], limit: int) -> list[dict]:
    """**A 级无条件保留，名额只约束 B 级。**

    此前是 `find_cliques(pairs)[:limit]`，按分数一刀切。分数 =
    `log1p(最弱共现) × 衰减^年龄 × 等级权重`，其中时间衰减是逐年指数的，
    等级权重只有 1.0 与 0.7 之差——一个 2021 年站住脚的 A 级组合会被衰减压到
    0.054，而 2026 年站住脚的 B 级组合保持原值，A 级因此整体沉到 98 个团里的
    第 61/75/83 名，被 limit=40 全数截掉，落库的 25 条**没有一条是 A 级**。

    这与分级输出的设计意图正相反：A 级的判据是「两侧技术在 JD 中均常见、
    独立性下本应共现却从未共现」，是本方法置信度最高的一档。名额是防止
    B 级刷屏用的，不该反过来把最可信的那几条挤掉。

    A 级本就稀少（当前 3 个），全留不会淹没结果。**排序仍按分数**——
    衰减对「这条线索还新不新」的刻画是对的，只是不该有生杀权。
    """
    high = [item for item in cliques if item["grade"] == "A"]
    rest = [item for item in cliques if item["grade"] != "A"]
    kept = high + rest[: max(0, limit - len(high))]
    kept.sort(key=lambda item: -item["score"])
    return kept


def _month_start(month: str) -> date:
    return date(int(month[:4]), int(month[5:7]), 1)


SYSTEM_PROMPT = (
    "你是岗位研究助手。给定一组技术，它们在学术论文与专利中已反复一起出现，"
    "但在招聘市场上从未被写进同一个岗位。请为这个能力组合拟一个岗位名称与说明。\n"
    "硬约束：\n"
    "1. 只能使用给定技术，不得新增技术、数字或应用领域。\n"
    "2. 名称要像中文招聘市场上真实会出现的职位名，通常 6–14 字，"
    "体现职责定位而非技术罗列；不要用顿号或「与」把技术并列充当名称。\n"
    "3. **不得声称该岗位已经存在或即将出现**。这是一个尚未在招聘市场出现的组合，"
    "说明文字应写成「该组合在研究侧已成形」，而不是「市场需要该岗位」。\n"
    "4. 证据不足时写明，不要编造。\n"
    "输出 JSON：{\"proposed_name\": ..., \"one_line_definition\": ..., "
    "\"core_responsibilities\": [...], \"formation_reason\": ...}"
)


def name_combination(names: list[str], evidence: dict) -> dict | None:
    result = generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=json.dumps(
            {
                "technologies": names,
                "upstream_cooccurrence": evidence["min_cooccurrence"],
                "established_month": evidence["established_month"],
                "gap_grade": evidence["grade"],
            },
            ensure_ascii=False,
        ),
        prompt_version=PROMPT_VERSION,
        json_mode=True,
    )
    return result.parsed_json if result and result.parsed_json else None


def collect_unverified(args: argparse.Namespace) -> list[dict]:
    """C 级技术点的待核查清单，按技术聚合。

    每条回答同一个问题：这个技术在上游语料里活跃，却在全部 JD 中一次都没出现——
    它是市场尚未覆盖的新技术，还是根本不属于具身智能招聘范围？本系统区分不了，
    需要人工判断，而判断一次即可复用到该技术涉及的所有缺口对上。
    """
    scoped = argparse.Namespace(**vars(args))
    scoped.grades = "C"
    aggregated: dict[str, dict] = {}
    for item in load_pairs(scoped):
        for side in (0, 1):
            code = item["pair"][side]
            if item["jd_mentions"][side] > 0:
                continue  # 只收 JD 中零出现的那一侧
            entry = aggregated.setdefault(
                code,
                {
                    "technology_code": code,
                    "pair_count": 0,
                    "max_upstream_cooccurrence": 0,
                    "earliest_established": item["established_month"],
                    "partners": [],
                },
            )
            entry["pair_count"] += 1
            entry["max_upstream_cooccurrence"] = max(
                entry["max_upstream_cooccurrence"], item["upstream_cooccurrence"]
            )
            entry["earliest_established"] = min(
                entry["earliest_established"], item["established_month"]
            )
            partner = item["pair"][1 - side]
            if partner not in entry["partners"]:
                entry["partners"].append(partner)
    rows = sorted(
        aggregated.values(),
        key=lambda item: (-item["max_upstream_cooccurrence"], item["technology_code"]),
    )
    return rows


def main() -> None:
    args = parse_args()
    pairs = load_pairs(args)
    if not pairs:
        raise SystemExit("没有 A/B 级缺口对，先跑 find_upstream_only_pairs 确认")
    cliques = apply_limit(find_cliques(pairs), args.limit)

    with SessionLocal() as session:
        version_id = session.scalar(
            select(TechnologyTaxonomyVersion.taxonomy_version_id)
            .where(TechnologyTaxonomyVersion.version_status_code == "active")
            .order_by(TechnologyTaxonomyVersion.effective_date.desc())
            .limit(1)
        )
        nodes = {
            node.technology_code: node
            for node in session.scalars(
                select(TechnologyNode).where(
                    TechnologyNode.taxonomy_version_id == version_id,
                    TechnologyNode.level_code == "L3",
                )
            )
        }
        clustering = session.scalar(
            select(JobClusteringRun)
            .where(JobClusteringRun.run_status_code == "success")
            .order_by(JobClusteringRun.clustering_run_id.desc())
        )

        stats: Counter[str] = Counter()
        print(f"缺口对 {len(pairs)} 个 → 能力组合 {len(cliques)} 个\n")
        if not args.execute:
            for clique in cliques[:25]:
                labels = [
                    nodes[code].technology_name if code in nodes else code
                    for code in clique["technology_codes"]
                ]
                print(
                    f"  [{clique['grade']}] {' + '.join(labels)}"
                    f"   最弱共现 {clique['min_cooccurrence']} 次"
                    f" · 站住脚 {clique['established_month']} · 分 {clique['score']}"
                )
            print("\n默认只预览。确认后加 --execute 落库。")
            return

        if not llm_available():
            raise SystemExit("LLM 网关不可用，无法生成岗位名；命名是本类候选的主要产出")

        run = DiscoveryRun(
            run_code=f"upstream_{uuid4().hex[:22]}",
            mode_code=MODE_CODE,
            target_date=date.today(),
            window_start_date=None,
            clustering_run_id=clustering.clustering_run_id,
            taxonomy_version_id=version_id,
            algorithm_version=ALGORITHM_VERSION,
            parameter_json={
                "min_cooccurrence": args.min_cooccurrence,
                "grades": args.grades,
                "max_combination_size": MAX_COMBINATION_SIZE,
            },
            input_snapshot_json={"pair_count": len(pairs), "clique_count": len(cliques)},
            input_snapshot_hash=uuid4().hex,
        )
        run.run_status_code = "running"
        run.started_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(run)
        session.flush()

        existing_keys = set(
            session.scalars(
                select(EmergingRoleCandidate.candidate_key).where(
                    EmergingRoleCandidate.classification_code == CLASSIFICATION
                )
            )
        )
        for clique in cliques:
            codes = clique["technology_codes"]
            # 候选身份 = 模式 + 技术组合，与运行无关；重跑时已存在的直接跳过，
            # 避免撞唯一键，也避免为同一组合反复调用 LLM 命名。
            if f"{MODE_CODE}|" + "-".join(codes) in existing_keys:
                stats["已存在，跳过"] += 1
                continue
            technologies = [nodes[c] for c in codes if c in nodes]
            if len(technologies) < 2:
                stats["技术点不在当前词表，跳过"] += 1
                continue
            labels = [item.technology_name for item in technologies]
            expression = name_combination(labels, clique)
            if expression is None:
                stats["命名失败，跳过"] += 1
                continue

            lag = estimate_transmission_lag(tuple(c.split(".")[0] for c in codes))
            card = {
                "fact_schema_version": "upstream_gap_card_v1",
                "source": "upstream_corpus",
                "gap_grade": clique["grade"],
                "technology_codes": codes,
                "technology_names": labels,
                "min_upstream_cooccurrence": clique["min_cooccurrence"],
                "established_month": clique["established_month"],
                # JD 侧的支撑量恒为 0——这正是本类候选的定义，不是数据缺失。
                "jd_cooccurrence": 0,
                "jd_mentions": {
                    item["names"][i]: item["jd_mentions"][i]
                    for item in clique["edges"]
                    for i in (0, 1)
                },
                "expected_transmission_lag": lag,
                "evidence_pairs": [
                    {
                        "pair": item["names"],
                        "upstream_cooccurrence": item["upstream_cooccurrence"],
                        "established_month": item["established_month"],
                        "grade": item["grade"],
                    }
                    for item in clique["edges"]
                ],
                "llm_boundary": "expression_only_no_fact_mutation",
                "caveat": (
                    "本候选来自上游语料（论文与专利）中已成形、而 JD 中从未出现的技术"
                    "组合。它是待核查的信号，不是已存在的岗位；参考区间由外部文献先验"
                    "推出，本系统无法验证，且 U-3 回测不支持「上游领先招聘」这一前提。"
                ),
            }
            candidate = EmergingRoleCandidate(
                discovery_run_id=run.discovery_run_id,
                task_community_id=None,
                candidate_code=f"upstream_{uuid4().hex[:20]}",
                candidate_key=f"{MODE_CODE}|" + "-".join(codes),
                proposed_name=str(expression.get("proposed_name", ""))[:500]
                or "·".join(labels) + "工程师",
                normalized_name="".join(labels),
                maturity_stage_code="potential",
                workflow_status_code="pending",
                candidate_score=clique["score"],
                support_job_count=0,
                nearest_job_role_id=None,
                overlap_score=0,
                classification_code=CLASSIFICATION,
                last_seen_discovery_run_id=run.discovery_run_id,
                mechanical_card_json=card,
                expression_json={
                    "name": expression.get("proposed_name"),
                    "one_line_definition": expression.get("one_line_definition"),
                    "core_responsibilities": expression.get("core_responsibilities") or [],
                    "formation_reason": expression.get("formation_reason"),
                    "generation_method": "llm_expression",
                },
                expression_model_version=f"llm:{PROMPT_VERSION}",
                risk_flags_json=["no_hiring_evidence"],
            )
            session.add(candidate)
            session.flush()
            for node in technologies:
                session.add(
                    CandidateTechnology(
                        emerging_role_candidate_id=candidate.emerging_role_candidate_id,
                        technology_node_id=node.technology_node_id,
                        requirement_type_code="required",
                        importance_score=1,
                        membership_code="core",
                    )
                )
            # **必须建审核任务。** 审核台的处置动作走
            # `POST /role-discovery/reviews/{task_code}/actions`，没有任务的候选在台上
            # 只能看不能处置。主流程（service.py）建候选时同步建任务，这里沿用同一形态，
            # 否则上游候选会成为审核台里一批点不动的条目。
            session.add(
                ReviewTask(
                    task_code=f"review_discovery_{candidate.candidate_code}",
                    queue_code="job_discovery",
                    target_type_code="emerging_role",
                    target_id=candidate.emerging_role_candidate_id,
                    priority_score=candidate.candidate_score,
                    task_status_code="queued",
                    target_snapshot_json=candidate_snapshot(session, candidate),
                    reason_json={
                        "risk_flags": candidate.risk_flags_json,
                        "grade": clique["grade"],
                        "source": "upstream_gap",
                    },
                )
            )
            stats["生成"] += 1
            print(f"  [{clique['grade']}] {' + '.join(labels)}\n      → {candidate.proposed_name}")

        unverified = collect_unverified(args)
        for row in unverified:
            node = nodes.get(row["technology_code"])
            row["technology_name"] = node.technology_name if node else row["technology_code"]
            row["partner_names"] = [
                nodes[c].technology_name if c in nodes else c for c in row["partners"]
            ][:8]

        run.run_status_code = "success"
        run.completed_at = datetime.now(UTC).replace(tzinfo=None)
        run.result_summary_json = {
            **dict(stats),
            # C 级待核查清单：审核台从这里读，API 不必去读语料文件。
            "unverified_technologies": unverified,
            "unverified_note": (
                "这些技术在上游语料中活跃，却在全部 JD 中一次都没出现。"
                "可能是市场尚未覆盖的新技术，也可能根本不属于具身智能招聘范围——"
                "本系统无法区分，需要人工判断。"
            ),
        }
        session.commit()
        print(f"\n{json.dumps(dict(stats), ensure_ascii=False)}")
        print(f"C 级待核查技术点：{len(unverified)} 个")
        print(f"推演运行：{run.run_code}")


if __name__ == "__main__":
    main()
