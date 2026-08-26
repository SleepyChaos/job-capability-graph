"""由「里程碑事件中已共现、而 JD 中从未共现」的技术组合生成岗位缺失候选。

**与上游共现路径的区别在证据的性质，不在算法。** 两条路都走
「找缺口对 → 分级 → 在缺口图上找团 → LLM 命名」，判据与找团逻辑直接复用
`find_upstream_only_pairs` 与 `build_upstream_candidates`，只有一处实现。

不同的是证据能指到什么：

| | 上游共现路径 | 本路径 |
| --- | --- | --- |
| 证据 | 两个技术在 N 篇论文/专利里一起出现 | 具体的、有日期的事件 |
| 锚点 | 共现累积到门槛的月份 | 事件发生当天 |
| 域偏离 | 严重（cs.RO 含大量无人机研究） | 无（里程碑是人工筛过的具身智能事件） |
| 数量 | 75 对缺口 | 31 对缺口 |

上游路径产出的 A 级里，「强化学习 + 无人机」几乎肯定是域偏离造成的假象——
本路径不会有这个问题，代价是量少。**两条路是互补的，不是替代关系**，因此
候选分成两类并列陈列（`upstream_signal` 与 `milestone_signal`），
不合并成一类。

**min-cooccurrence 默认为 1，与上游路径的 3 不同。** 一条论文里的偶然共现说明不了
什么，所以上游要求累积 3 次；而一次有日期、有主体的产品发布或技术突破本身就是
一个完整事实，要求它重复三次等于把最新的信号全滤掉——里程碑总共才 301 条可用。

**仍然无法验证。** 与上游路径一样，「这个岗位将来会出现」只能等未来的 JD 检验。
本路径改善的是证据质量，不是结论强度。

用法（backend 目录 / 容器内）：
    python -m tools.build_milestone_candidates \\
        --extracted /srv/data/upstream/milestone_extracted [--execute]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, text

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
from tools import build_upstream_candidates as upstream

MODE_CODE = "milestone_gap"
CLASSIFICATION = "milestone_signal"
ALGORITHM_VERSION = "milestone_gap_v1"
PROMPT_VERSION = "milestone_combination_naming_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="由里程碑缺口组合生成岗位候选。")
    parser.add_argument("--extracted", type=Path, required=True)
    parser.add_argument(
        "--min-cooccurrence",
        type=int,
        default=1,
        help="一次有日期、有主体的事件本身即为完整事实，默认 1；上游路径用 3",
    )
    parser.add_argument("--grades", default="A,B", help="纳入候选池的等级")
    parser.add_argument(
        "--limit", type=int, default=40, help="B 级候选的名额上限；A 级不受限，全部保留"
    )
    parser.add_argument("--execute", action="store_true", help="真正落库（默认只预览）")
    return parser.parse_args()


def load_milestones(directory: Path) -> dict[tuple[str, str], list[dict]]:
    """每个技术对背后的里程碑事件，按日期升序。

    这是本工具相对上游路径唯一新增的数据结构：上游只需要共现次数与日期，
    而里程碑路径的价值恰恰在于**能把候选指回具体事件**，因此要把事件本身留住。
    """
    from itertools import combinations

    events: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for shard in sorted(directory.glob("tech_*.jsonl")):
        for line in shard.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            codes = sorted(set(row["technology_codes"]))
            event = {
                "milestone_code": row["arxiv_id"],
                "milestone_name": row.get("milestone_name"),
                "milestone_type_code": row.get("milestone_type_code"),
                "event_date": row["published"],
            }
            for pair in combinations(codes, 2):
                events[pair].append(event)
    return {
        pair: sorted(items, key=lambda item: item["event_date"])
        for pair, items in events.items()
    }


SYSTEM_PROMPT = (
    "你是岗位研究助手。给定一组技术，它们在具身智能领域的**具体里程碑事件**"
    "（产品发布、技术突破、开源、标准发布等）中已经一起出现，"
    "但在招聘市场上从未被写进同一个岗位。请为这个能力组合拟一个岗位名称与说明。\n"
    "硬约束：\n"
    "1. 只能使用给定技术，不得新增技术、数字或应用领域。\n"
    "2. 名称要像中文招聘市场上真实会出现的职位名，通常 6–14 字，"
    "体现职责定位而非技术罗列；不要用顿号或「与」把技术并列充当名称。\n"
    "3. **不得声称该岗位已经存在或即将出现**，也不得声称某家公司在招这个岗位。"
    "给定的里程碑只说明该技术组合在产业侧已经出现过，不说明有人在为它招聘。\n"
    "4. formation_reason 要写这个能力组合为什么会形成一类工作，"
    "而不是写你为什么这样命名。\n"
    "5. 证据不足时写明，不要编造。\n"
    '输出 JSON：{"proposed_name": ..., "one_line_definition": ..., '
    '"core_responsibilities": [...], "formation_reason": ...}'
)


def name_combination(names: list[str], evidence: dict) -> dict | None:
    result = generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=json.dumps(
            {
                "technologies": names,
                "milestone_events": [
                    {
                        "name": item["milestone_name"],
                        "type": item["milestone_type_code"],
                        "date": item["event_date"],
                    }
                    for item in evidence["milestones"][:6]
                ],
                "jd_cooccurrence": 0,
                "gap_grade": evidence["grade"],
            },
            ensure_ascii=False,
        ),
        prompt_version=PROMPT_VERSION,
        json_mode=True,
    )
    if not result or not result.parsed_json:
        return None
    payload = result.parsed_json
    return payload if payload.get("proposed_name") else None


def main() -> None:
    args = parse_args()
    pairs = upstream.load_pairs(args)
    if not pairs:
        raise SystemExit("没有 A/B 级缺口对，先跑 find_upstream_only_pairs 确认")
    cliques = upstream.apply_limit(upstream.find_cliques(pairs), args.limit)
    milestones = load_milestones(args.extracted)

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
        verified = {
            row[0]
            for row in session.execute(
                text(
                    "SELECT milestone_code FROM biz_milestone_event "
                    "WHERE verification_status_code = 'verified'"
                )
            ).all()
        }

        stats: Counter[str] = Counter()
        print(f"缺口对 {len(pairs)} 个 → 能力组合 {len(cliques)} 个\n")
        if not args.execute:
            for clique in cliques:
                labels = [
                    nodes[code].technology_name if code in nodes else code
                    for code in clique["technology_codes"]
                ]
                events = _events_for(clique, milestones)
                print(
                    f"  [{clique['grade']}] {' + '.join(labels)}"
                    f"   依据 {len(events)} 条里程碑 · 最早 {clique['established_month']}"
                )
                for item in events[:2]:
                    print(
                        f"        {item['event_date']} {item['milestone_type_code']}"
                        f" · {item['milestone_name']}"
                    )
            print("\n默认只预览。确认后加 --execute 落库。")
            return

        if not llm_available():
            raise SystemExit("LLM 网关不可用，无法生成岗位名；命名是本类候选的主要产出")

        run = DiscoveryRun(
            run_code=f"milestone_{uuid4().hex[:21]}",
            mode_code=MODE_CODE,
            target_date=date.today(),
            window_start_date=None,
            clustering_run_id=clustering.clustering_run_id,
            taxonomy_version_id=version_id,
            algorithm_version=ALGORITHM_VERSION,
            parameter_json={
                "min_cooccurrence": args.min_cooccurrence,
                "grades": args.grades,
                "max_combination_size": upstream.MAX_COMBINATION_SIZE,
            },
            input_snapshot_json={
                "pair_count": len(pairs),
                "clique_count": len(cliques),
                "milestone_pair_count": len(milestones),
            },
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
            if f"{MODE_CODE}|" + "-".join(codes) in existing_keys:
                stats["已存在，跳过"] += 1
                continue
            technologies = [nodes[c] for c in codes if c in nodes]
            if len(technologies) < 2:
                stats["技术点不在当前词表，跳过"] += 1
                continue
            labels = [item.technology_name for item in technologies]
            events = _events_for(clique, milestones)
            if not events:
                # 找团时新加进来的边可能来自另一个技术对，其里程碑未必与原对同属
                # 一条事件。没有事件可指的组合不该走本路径——它的立论基础就是
                # 「能指回具体事件」。
                stats["无可指认的里程碑事件，跳过"] += 1
                continue
            expression = name_combination(labels, {**clique, "milestones": events})
            if expression is None:
                stats["命名失败，跳过"] += 1
                continue

            lag = estimate_transmission_lag(tuple(c.split(".")[0] for c in codes))
            card = {
                "fact_schema_version": "milestone_gap_card_v1",
                "source": "milestone_events",
                "gap_grade": clique["grade"],
                "technology_codes": codes,
                "technology_names": labels,
                "milestone_count": len(events),
                "verified_milestone_count": sum(
                    1 for item in events if item["milestone_code"] in verified
                ),
                "established_month": clique["established_month"],
                "jd_cooccurrence": 0,
                "jd_mentions": {
                    item["names"][i]: item["jd_mentions"][i]
                    for item in clique["edges"]
                    for i in (0, 1)
                },
                "expected_transmission_lag": lag,
                "milestones": events[:12],
                "llm_boundary": "expression_only_no_fact_mutation",
                "caveat": (
                    # 这段话直接渲染成正文，不走 Markdown，不能带星号标记。
                    "本候选的依据是具身智能领域里程碑事件中已共现、而全部 JD 中从未"
                    "共现的技术组合。里程碑说明该组合在产业侧已经出现过，"
                    "并不说明有人在为它招聘；它是待核查的信号，不是已存在的岗位。"
                    "参考区间由外部文献先验推出，本系统无法验证。"
                ),
            }
            candidate = EmergingRoleCandidate(
                discovery_run_id=run.discovery_run_id,
                task_community_id=None,
                candidate_code=f"milestone_{uuid4().hex[:19]}",
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
                        "source": "milestone_gap",
                    },
                )
            )
            stats["生成"] += 1
            print(f"  [{clique['grade']}] {' + '.join(labels)}\n      → {candidate.proposed_name}")

        run.run_status_code = "success"
        run.completed_at = datetime.now(UTC).replace(tzinfo=None)
        run.result_summary_json = {
            **dict(stats),
            "note": (
                "里程碑事件中已共现、而 JD 中从未共现的技术组合。里程碑证明该组合"
                "在产业侧已经出现，不证明有人在招；本系统无法验证该岗位是否会出现。"
            ),
        }
        session.commit()
        print(f"\n{json.dumps(dict(stats), ensure_ascii=False)}")
        print(f"推演运行：{run.run_code}")


def _events_for(clique: dict, milestones: dict[tuple[str, str], list[dict]]) -> list[dict]:
    """组合背后的全部里程碑事件，按日期升序去重。

    只取**组合内每一条边**都命中的事件不现实（一条里程碑很少同时提到三个技术），
    因此取并集：任意一条边有证据即列出，由审阅者看事件本身判断分量。
    这是刻意的宽口径——本路径的产出是给人看的线索，不是自动结论。
    """
    seen: dict[str, dict] = {}
    codes = clique["technology_codes"]
    for index, left in enumerate(codes):
        for right in codes[index + 1 :]:
            for item in milestones.get((left, right), []):
                seen.setdefault(item["milestone_code"], item)
    return sorted(seen.values(), key=lambda item: item["event_date"])


if __name__ == "__main__":
    main()
