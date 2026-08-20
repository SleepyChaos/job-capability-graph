"""留出重发现的基线对照：本方法 vs 频次基线 vs 名称基线。

留出实验单独跑只能说明「系统能不能把被遮蔽的岗位找回来」，说明不了「这是不是因为
方法本身好」。要回答后者，必须让别的方法在**完全相同的遮蔽集、完全相同的评测函数**
下跑同一件事。

三条臂：

- `system`     本方法：频繁闭项集挖掘 → 非对称覆盖率 → 证据门控（由 run_discovery 产出）
- `frequency`  频次基线：直接把每份 JD 的技术集合当候选，按重复出现次数排序。
               没有项集挖掘、没有闭包、没有组合大小加权——用来隔离「粒度设计」的贡献。
- `title`      名称基线：按岗位名称词元重合度把 JD 分组，组内多数技术构成候选，按组规模排序。
               这就是文档 7.1 所批评的「事后归纳」范式的直接实现。

**名称基线是三条里最关键的一条**：本方法的立论前提是「岗位由能力集合定义，名称是
不稳定标签」。若按名称归纳能同样好地找回被遮蔽岗位，这个前提就不成立。

三条臂共用 `run_holdout_experiment.evaluate()` 计算指标，且共用同一个遮蔽集
（由 eligible 岗位集合 + mask_ratio + seed 纯函数导出），保证可比。

用法（backend 目录 / 容器内）：
    python -m tools.experiment_holdout_baselines --target-date 2026-08-31 --seed 20260820
    python -m tools.experiment_holdout_baselines --target-date 2026-08-31 --dry-run
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.modules.clustering.models import JobClusteringRun
from app.modules.discovery.models import DiscoveryRun, EmergingRoleCandidate
from app.modules.discovery.service import (
    ALGORITHM_VERSION,
    DEFAULT_PARAMETERS,
    run_discovery,
)
from app.modules.extraction.job_structure import cluster_tokens
from app.modules.job.models import (
    JobPosting,
    JobRequirement,
    TechnologyMatchAssessment,
)
from app.modules.taxonomy.models import TechnologyNode
from tools.run_holdout_experiment import (
    DEFAULT_JACCARD_THRESHOLD,
    DEFAULT_MASK_RATIO,
    RECALL_KS,
    CandidateProfile,
    build_mask_set,
    containment,
    eligible_mask_roles,
    evaluate,
    jaccard,
    load_run_candidates,
)

EXPERIMENT_VERSION = "holdout_baselines_v1"
# 名称基线把标题词元重合度达到该值的 JD 归为一组。
TITLE_GROUP_JACCARD = 0.5
# 组内出现比例达到该值的技术才进入名称基线的候选能力集（对应「核心能力」的朴素版本）。
TITLE_MAJORITY_RATIO = 0.5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="留出重发现的基线对照实验。")
    parser.add_argument("--target-date", type=date.fromisoformat, required=True)
    parser.add_argument("--seed", type=int, default=20260820)
    parser.add_argument(
        "--seeds",
        default="",
        help=(
            "逗号分隔的多个种子；给出时对每个种子各跑一轮并汇总。"
            "能力等价组只有几十个，单轮遮蔽目标太少，多轮汇总才有统计意义。"
        ),
    )
    parser.add_argument(
        "--current-algorithm-only",
        action="store_true",
        default=True,
        help=(
            "只保留由当前算法版本首次提出的候选。候选按稳定键去重，旧版本产出的"
            "候选会被刷新后长期留在池中，其技术组合用的是已废弃的粒度口径，"
            "与当前候选不可比。"
        ),
    )
    parser.add_argument(
        "--include-legacy-candidates",
        dest="current_algorithm_only",
        action="store_false",
        help="保留旧算法版本的候选（用于量化旧候选对名额的稀释）",
    )
    parser.add_argument("--mask-ratio", type=float, default=DEFAULT_MASK_RATIO)
    parser.add_argument("--jaccard-threshold", type=float, default=DEFAULT_JACCARD_THRESHOLD)
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=100,
        help="每条臂参与排名的候选上限；三条臂取同一上限以保证 Recall@K 可比",
    )
    parser.add_argument(
        "--mask-unit",
        choices=["role", "group"],
        default="group",
        help=(
            "遮蔽单位。role=按单个岗位（原协议）；group=按能力等价组（修正协议）。"
            "岗位库存在大量近重复，按单个岗位遮蔽等于没遮——遮掉的能力组合仍被其"
            "近重复覆盖，实验失去区分力。"
        ),
    )
    parser.add_argument(
        "--diagnose-mask",
        action="store_true",
        help="只检查遮蔽是否有效：统计每个被遮蔽岗位还剩多少个近重复岗位没被遮蔽",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印遮蔽集与各臂候选规模，不调用 run_discovery",
    )
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    return parser.parse_args()


def load_job_technologies(
    db: Session, parse_run_id: int, target_date: date
) -> dict[int, tuple[str, frozenset[str]]]:
    """JD → (岗位名, 已接受的技术编码集合)。口径与推演侧证据收集一致。

    用技术编码而非节点 id：节点 id 逐词表版本独立，与岗位画像比较时必须落在
    同一个标识空间里，否则交集恒为空。
    """
    cutoff = datetime.combine(target_date, datetime.max.time())
    rows = db.execute(
        select(
            JobPosting.job_posting_id,
            JobPosting.job_title_normalized,
            TechnologyNode.technology_code,
        )
        .join(JobRequirement, JobRequirement.job_posting_id == JobPosting.job_posting_id)
        .join(
            TechnologyNode,
            TechnologyNode.technology_node_id == JobRequirement.technology_node_id,
        )
        .join(
            TechnologyMatchAssessment,
            TechnologyMatchAssessment.job_requirement_id == JobRequirement.job_requirement_id,
        )
        .where(
            JobRequirement.technology_node_id.is_not(None),
            TechnologyMatchAssessment.job_parse_run_id == parse_run_id,
            TechnologyMatchAssessment.assessment_status_code == "accepted",
            or_(
                JobPosting.source_collected_at <= cutoff,
                (JobPosting.source_collected_at.is_(None)) & (JobPosting.published_at <= cutoff),
            ),
        )
    ).all()
    titles: dict[int, str] = {}
    technologies: dict[int, set[str]] = defaultdict(set)
    for job_id, title, technology_code in rows:
        titles[job_id] = title or ""
        technologies[job_id].add(technology_code)
    return {job_id: (titles[job_id], frozenset(ids)) for job_id, ids in technologies.items()}


def frequency_candidates(
    jobs: dict[int, tuple[str, frozenset[str]]], limit: int
) -> list[CandidateProfile]:
    """频次基线：把每份 JD 的完整技术集合当作一个候选，按重复出现的 JD 数排序。

    不做项集挖掘、不做闭包、不按组合大小加权——它代表「只看共现频次」能达到的水平。
    """
    counts = Counter(technologies for _title, technologies in jobs.values() if technologies)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], sorted(item[0])))
    return [
        CandidateProfile(
            candidate_code=f"freq-{index:04d}",
            score=float(count),
            technology_codes=technologies,
            classification_code="baseline_frequency",
        )
        for index, (technologies, count) in enumerate(ranked[:limit], start=1)
    ]


def title_candidates(
    jobs: dict[int, tuple[str, frozenset[str]]], limit: int
) -> list[CandidateProfile]:
    """名称基线：按岗位名称词元重合度分组，组内多数技术构成候选，按组规模排序。

    这是「事后归纳」范式的直接实现：先按名字把 JD 归到一起，再从组里提取共性能力。
    分组用贪心 leader，JD 按 (岗位名, id) 确定性排序后依次进入，保证可重放。
    """
    tokenized = {
        job_id: frozenset(cluster_tokens(title))
        for job_id, (title, _technologies) in jobs.items()
    }
    groups: list[tuple[frozenset[str], list[int]]] = []
    for job_id in sorted(jobs, key=lambda key: (jobs[key][0], key)):
        tokens = tokenized[job_id]
        if not tokens:
            continue
        placed = False
        for index, (leader_tokens, members) in enumerate(groups):
            union = leader_tokens | tokens
            overlap = len(leader_tokens & tokens) / len(union) if union else 0.0
            if overlap >= TITLE_GROUP_JACCARD:
                groups[index] = (leader_tokens, [*members, job_id])
                placed = True
                break
        if not placed:
            groups.append((tokens, [job_id]))

    profiles: list[tuple[int, frozenset[str]]] = []
    for _leader_tokens, members in groups:
        counter: Counter[str] = Counter()
        for job_id in members:
            counter.update(jobs[job_id][1])
        threshold = max(1, int(len(members) * TITLE_MAJORITY_RATIO))
        majority = frozenset(tech for tech, count in counter.items() if count >= threshold)
        if majority:
            profiles.append((len(members), majority))

    profiles.sort(key=lambda item: (-item[0], sorted(item[1])))
    return [
        CandidateProfile(
            candidate_code=f"title-{index:04d}",
            score=float(size),
            technology_codes=technologies,
            classification_code="baseline_title",
        )
        for index, (size, technologies) in enumerate(profiles[:limit], start=1)
    ]


def capability_groups(
    eligible: dict[int, tuple[str, frozenset[str]]], threshold: float
) -> list[list[int]]:
    """把能力画像互为近重复的岗位归为一组——取「Jaccard ≥ 阈值」关系下的连通分量。

    岗位库里同一能力组合往往对应多个岗位（反复聚类产生的近重复）。留出实验若按单个
    岗位遮蔽，被遮蔽岗位的能力组合仍被其近重复覆盖，参照系没有真正改变。

    **必须取连通分量而非贪心分组。** 贪心 leader 会把「与组长不相似、但与组内其它成员
    相似」的岗位分到别组，遮蔽整组后仍有近重复幸存（实测遮蔽有效率只有 0.46）。
    连通分量保证互为近重复的岗位一定同组，遮蔽才彻底。
    """
    role_ids = sorted(eligible)
    parent = {role_id: role_id for role_id in role_ids}

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for index, left in enumerate(role_ids):
        for right in role_ids[index + 1 :]:
            if jaccard(eligible[left][1], eligible[right][1]) >= threshold:
                parent[find(right)] = find(left)

    components: dict[int, list[int]] = defaultdict(list)
    for role_id in role_ids:
        components[find(role_id)].append(role_id)
    # 组内按 id 升序、组间按（规模降序, 首个 id）排序，保证可重放。
    return sorted((sorted(group) for group in components.values()), key=lambda g: (-len(g), g[0]))


def diagnose_mask(
    eligible: dict[int, tuple[str, frozenset[str]]],
    masked_ids: list[int],
    threshold: float,
) -> dict:
    """检查遮蔽是否真正把某个能力组合移出了参照系。

    留出实验的隐含假设是「遮蔽某岗位后，它的能力组合就不再被既有岗位覆盖」。
    若岗位库里存在大量近重复，遮掉一个而其近重复仍在，该假设不成立——
    此时系统把对应候选判为「已被既有岗位覆盖」并不是错，实验本身失去了区分力。
    """
    masked = set(masked_ids)
    survivors: list[dict] = []
    for role_id in masked_ids:
        name, technologies = eligible[role_id]
        twins = [
            other_id
            for other_id, (_name, other_tech) in eligible.items()
            if other_id not in masked and jaccard(technologies, other_tech) >= threshold
        ]
        survivors.append({
            "role_id": role_id,
            "role_name": name,
            "surviving_twin_count": len(twins),
        })
    with_twins = [item for item in survivors if item["surviving_twin_count"] > 0]
    counts = sorted(item["surviving_twin_count"] for item in survivors)
    return {
        "masked_role_count": len(masked_ids),
        "roles_with_surviving_twin": len(with_twins),
        "effective_mask_ratio": round(1 - len(with_twins) / len(masked_ids), 4),
        "twin_count_median": counts[len(counts) // 2],
        "twin_count_max": counts[-1],
        "examples": sorted(survivors, key=lambda item: -item["surviving_twin_count"])[:10],
    }


def filter_current_algorithm(
    db: Session, candidates: list[CandidateProfile]
) -> list[CandidateProfile]:
    """只保留由当前算法版本首次提出的候选。

    候选按稳定键去重，旧版本产出的候选被刷新后会继续占据排名名额，而它们的技术组合
    是用已废弃的粒度口径挖出来的（实测一次运行的 100 个候选里 73 个来自旧版本，
    其中 58 个仍是二元组），与当前候选放在一起排名不可比。
    """
    versions = {
        run_code: version
        for run_code, version in db.execute(
            select(DiscoveryRun.run_code, DiscoveryRun.algorithm_version)
        )
    }
    kept = []
    for candidate in candidates:
        row = db.scalar(
            select(EmergingRoleCandidate).where(
                EmergingRoleCandidate.candidate_code == candidate.candidate_code
            )
        )
        first_seen = (row.mechanical_card_json or {}).get("first_seen_run_code") if row else None
        if versions.get(first_seen) == ALGORITHM_VERSION:
            kept.append(candidate)
    return kept


def arm_metrics(
    candidates: list[CandidateProfile],
    masked_roles: dict[int, tuple[str, frozenset[str]]],
    args: argparse.Namespace,
) -> dict:
    metrics = evaluate(
        candidates,
        masked_roles,
        jaccard_threshold=args.jaccard_threshold,
        seed=args.seed,
    )
    metrics["containment"] = evaluate(
        candidates,
        masked_roles,
        jaccard_threshold=args.jaccard_threshold,
        seed=args.seed,
        similarity_fn=containment,
    )
    # 候选与岗位画像的规模差直接决定对称 Jaccard 能取到多高：候选只有 3 个技术而
    # 岗位画像有 12 个时，即使候选完全落在画像内，Jaccard 也只有 0.25。
    sizes = sorted(len(item.technology_codes) for item in candidates)
    metrics["candidate_size"] = {
        "median": sizes[len(sizes) // 2] if sizes else 0,
        "mean": round(sum(sizes) / len(sizes), 2) if sizes else 0,
        "max": sizes[-1] if sizes else 0,
    }
    return metrics


ARMS = (
    ("system", "本方法：闭项集生成 + 证据门控排序"),
    ("hybrid", "混合臂：闭项集生成 + 支撑量排序"),
    ("frequency", "频次基线：JD 集合生成 + 支撑量排序"),
    ("title", "名称基线：按岗位名称归纳"),
    ("oracle", "oracle 排序（上界，仅供参照）"),
)


def oracle_metrics(
    candidates: list[CandidateProfile],
    masked_roles: dict[int, tuple[str, frozenset[str]]],
    args: argparse.Namespace,
) -> dict:
    """排序上界：把候选按「与任一被遮蔽岗位的最佳匹配度」降序排。

    它不是一个可实现的方法（用到了答案），只用来界定「改排序最多能到哪」。
    两种判据各自有自己的最优排序，因此分别排一次。
    """

    def ranked_by(similarity_fn) -> list[CandidateProfile]:
        """贪心集合覆盖：每次挑「能新命中最多尚未命中岗位」的候选。

        不能简单按最佳匹配度降序排——那会把匹配同一个岗位的候选全堆在前面，
        而 Recall@K 数的是命中了多少**不同**的岗位。按覆盖增量贪心才是
        Recall@K 的正确上界近似。
        """
        remaining = {
            role_id: tech for role_id, (_name, tech) in masked_roles.items()
        }
        pool = sorted(candidates, key=lambda item: item.candidate_code)
        ordered: list[CandidateProfile] = []
        while pool and remaining:
            best_candidate = None
            best_hits: list[int] = []
            for candidate in pool:
                hits = [
                    role_id
                    for role_id, tech in remaining.items()
                    if similarity_fn(tech, candidate.technology_codes) >= args.jaccard_threshold
                ]
                if len(hits) > len(best_hits):
                    best_candidate, best_hits = candidate, hits
            if best_candidate is None or not best_hits:
                break
            ordered.append(best_candidate)
            pool.remove(best_candidate)
            for role_id in best_hits:
                remaining.pop(role_id, None)
        return ordered + pool

    metrics = arm_metrics(ranked_by(jaccard), masked_roles, args)
    # 包含度口径下的上界要用包含度自己的最优排序，否则低估天花板。
    metrics["containment"] = evaluate(
        ranked_by(containment),
        masked_roles,
        jaccard_threshold=args.jaccard_threshold,
        seed=args.seed,
        similarity_fn=containment,
    )
    return metrics


def run_one_seed(session: Session, args: argparse.Namespace, seed: int) -> dict:
    """跑一个种子：构造遮蔽集 → 遮蔽状态下推演 → 三条臂在同一遮蔽集上评测。"""
    min_technology_count = int(DEFAULT_PARAMETERS["min_role_technology_count"])
    eligible = eligible_mask_roles(session, args.target_date, min_technology_count)
    if not eligible:
        raise SystemExit("没有满足资格线的岗位，无法构造遮蔽集")

    groups = capability_groups(eligible, args.jaccard_threshold)
    if args.mask_unit == "group":
        masked_reps = set(build_mask_set([g[0] for g in groups], args.mask_ratio, seed))
        masked_groups = [g for g in groups if g[0] in masked_reps]
        masked_ids = sorted(rid for group in masked_groups for rid in group)
        # 每组只计一个目标：一组近重复代表同一件事，逐个计分会把它重复计数。
        # 代表取技术集合最大的成员。
        masked_roles = {}
        for group in masked_groups:
            representative = max(group, key=lambda rid: (len(eligible[rid][1]), rid))
            masked_roles[representative] = eligible[representative]
    else:
        masked_ids = build_mask_set(sorted(eligible), args.mask_ratio, seed)
        masked_roles = {rid: eligible[rid] for rid in masked_ids}

    clustering_run = session.scalar(
        select(JobClusteringRun)
        .where(JobClusteringRun.run_status_code == "success")
        .order_by(JobClusteringRun.target_date.desc(), JobClusteringRun.clustering_run_id.desc())
    )
    if clustering_run is None:
        raise SystemExit("不存在成功的聚类运行")
    jobs = load_job_technologies(session, clustering_run.job_parse_run_id, args.target_date)

    discovery = run_discovery(
        session,
        mode_code="automatic",
        target_date=args.target_date,
        parameters={"excluded_role_ids": masked_ids},
    )
    if discovery.already_completed:
        # 候选按稳定键全局去重，last_seen_run_code 会被后跑的运行覆盖；命中重放缓存时
        # 推演不刷新候选，读回来的候选集会残缺甚至为空，指标全是垃圾。
        # 这类污染在结果里表现为「候选数骤降、技术数均值接近 0」，很容易被当成结论。
        raise SystemExit(
            f"种子 {seed} 的推演命中重放缓存（run_code={discovery.run_code}）。"
            "多轮实验必须使用从未跑过的种子，请换一组 --seeds。"
        )
    system = load_run_candidates(session, discovery.run_code)
    legacy_total = len(system)
    if args.current_algorithm_only:
        system = filter_current_algorithm(session, system)
    system = system[: args.candidate_limit]

    # 混合臂：与本方法完全相同的候选集合，只把排序换成支撑 JD 数。
    # 它把「生成」与「排序」分开——两臂候选一致，差异只能来自排序。
    hybrid = sorted(system, key=lambda item: (-item.support, item.candidate_code))
    candidates_by_arm = {
        "system": system,
        "hybrid": hybrid,
        "frequency": frequency_candidates(jobs, args.candidate_limit),
        "title": title_candidates(jobs, args.candidate_limit),
    }
    arms = {
        key: arm_metrics(candidates_by_arm[key], masked_roles, args)
        for key, _label in ARMS
        if key in candidates_by_arm
    }
    arms["oracle"] = oracle_metrics(system, masked_roles, args)
    return {
        "seed": seed,
        "discovery_run_code": discovery.run_code,
        "eligible_role_count": len(eligible),
        "capability_group_count": len(groups),
        "masked_role_count": len(masked_ids),
        "masked_target_count": len(masked_roles),
        "candidate_pool_before_filter": legacy_total,
        "masked_profile_sizes": sorted(len(t) for _n, t in masked_roles.values()),
        "arms": arms,
    }


def pool(rounds: list[dict]) -> dict:
    """把多轮结果汇总：Recall@K 按目标实例数加权平均，其余取合计。"""
    pooled: dict[str, dict] = {}
    for key, _label in ARMS:
        totals = {str(k): 0.0 for k in RECALL_KS}
        contain = {str(k): 0.0 for k in RECALL_KS}
        matched = targets = 0
        jaccards: list[float] = []
        sizes: list[float] = []
        for item in rounds:
            metrics = item["arms"][key]
            n = metrics["masked_role_count"]
            targets += n
            matched += metrics["matched_role_count"]
            for k in RECALL_KS:
                totals[str(k)] += metrics["recall_at_k"][str(k)] * n
                contain[str(k)] += metrics["containment"]["recall_at_k"][str(k)] * n
            if metrics["jaccard_summary"]["mean"] is not None:
                jaccards.append(metrics["jaccard_summary"]["mean"] * n)
            sizes.append(metrics["candidate_size"]["mean"])
        pooled[key] = {
            "target_count": targets,
            "matched_count": matched,
            "recall_at_k": {k: v / targets for k, v in totals.items()},
            "containment_recall_at_k": {k: v / targets for k, v in contain.items()},
            "mean_best_jaccard": sum(jaccards) / targets if targets else 0.0,
            "mean_candidate_size": round(sum(sizes) / len(sizes), 2) if sizes else 0,
            "candidate_count": round(
                sum(item["arms"][key]["candidate_count"] for item in rounds) / len(rounds), 1
            ),
        }
    random_totals = {str(k): 0.0 for k in RECALL_KS}
    targets = 0
    for item in rounds:
        metrics = item["arms"]["system"]
        n = metrics["masked_role_count"]
        targets += n
        for k in RECALL_KS:
            random_totals[str(k)] += metrics["random_baseline_recall_at_k"][str(k)] * n
    pooled["random"] = {"recall_at_k": {k: v / targets for k, v in random_totals.items()}}
    return pooled


def render(rounds: list[dict], pooled: dict, args: argparse.Namespace) -> None:
    first = rounds[0]
    seeds = ", ".join(str(item["seed"]) for item in rounds)
    print(f"# 留出重发现基线对照（{EXPERIMENT_VERSION}）\n")
    print(
        f"- 目标日期：{args.target_date} · 遮蔽比例：{args.mask_ratio}"
        f" · 遮蔽单位：{args.mask_unit}"
    )
    print(f"- 种子：{seeds}（冻结）·  轮数：{len(rounds)}")
    print(
        f"- 合格岗位 {first['eligible_role_count']} 个 →"
        f" 能力等价组 {first['capability_group_count']} 组"
    )
    print(
        f"- 每轮遮蔽 {first['masked_role_count']} 个岗位 /"
        f" {first['masked_target_count']} 个目标，"
        f"汇总 {pooled['system']['target_count']} 个目标实例"
    )
    if args.current_algorithm_only:
        print(f"- 候选只取当前算法版本 `{ALGORITHM_VERSION}` 首次提出的"
              f"（过滤前 {first['candidate_pool_before_filter']} 个）")
    sizes = first["masked_profile_sizes"]
    print(f"- 被遮蔽岗位画像技术数中位：{sizes[len(sizes) // 2]}\n")

    for title, field in (
        (f"对称 Jaccard ≥ {args.jaccard_threshold:.2f}（保守口径）", "recall_at_k"),
        (
            f"非对称包含度 ≥ {args.jaccard_threshold:.2f}（与推演侧同口径）",
            "containment_recall_at_k",
        ),
    ):
        print(f"## Recall@K —— {title}\n")
        header = " | ".join(f"@{k}" for k in RECALL_KS)
        print(f"| 方法 | 候选数 | 候选技术数均值 | {header} |")
        print("| --- | ---: | ---: | " + " | ".join(["---:"] * len(RECALL_KS)) + " |")
        for key, label in ARMS:
            row = pooled[key]
            cells = " | ".join(f"{row[field][str(k)]:.1%}" for k in RECALL_KS)
            print(
                f"| {label} | {row['candidate_count']} |"
                f" {row['mean_candidate_size']} | {cells} |"
            )
        if field == "recall_at_k":
            cells = " | ".join(f"{pooled['random']['recall_at_k'][str(k)]:.1%}" for k in RECALL_KS)
            print(f"| 随机排序（本方法候选集） | — | — | {cells} |")
        smallest = min(pooled[key]["candidate_count"] for key, _ in ARMS)
        print(f"\n> 各臂候选数不等，只有 K ≤ {int(smallest)} 的列可比；"
              f"K 超过某臂候选数时该臂的 Recall 被池子大小卡住，不反映排序能力。")
        print()


def main() -> None:
    args = parse_args()
    seeds = [int(x) for x in args.seeds.split(",") if x.strip()] or [args.seed]

    with SessionLocal() as session:
        if args.diagnose_mask or args.dry_run:
            min_technology_count = int(DEFAULT_PARAMETERS["min_role_technology_count"])
            eligible = eligible_mask_roles(session, args.target_date, min_technology_count)
            groups = capability_groups(eligible, args.jaccard_threshold)
            if args.mask_unit == "group":
                reps = set(build_mask_set([g[0] for g in groups], args.mask_ratio, args.seed))
                masked_ids = sorted(
                    rid for group in groups if group[0] in reps for rid in group
                )
            else:
                masked_ids = build_mask_set(sorted(eligible), args.mask_ratio, args.seed)
            if args.diagnose_mask:
                print(json.dumps(
                    diagnose_mask(eligible, masked_ids, args.jaccard_threshold),
                    ensure_ascii=False, indent=2,
                ))
            else:
                print(json.dumps({
                    "eligible_role_count": len(eligible),
                    "capability_group_count": len(groups),
                    "masked_role_count": len(masked_ids),
                    "dry_run": True,
                }, ensure_ascii=False, indent=2))
            return

        rounds = [run_one_seed(session, args, seed) for seed in seeds]

    pooled = pool(rounds)
    if args.format == "json":
        print(json.dumps({"rounds": rounds, "pooled": pooled}, ensure_ascii=False))
        return
    render(rounds, pooled, args)


if __name__ == "__main__":
    main()
