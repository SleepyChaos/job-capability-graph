"""留出重发现实验(holdout re-discovery)——实验协议脚本。

协议(docs/07 任务组 6 / docs/10 窗口 A-3,只工程实现不改设计):
  1. 从正式岗位中选「生效版本技术词 >= 资格线(默认与推演参数
     min_role_technology_count 对齐)」者,按 mask_ratio 与 seed 确定性采样出遮蔽集;
  2. 以 automatic 模式调用 run_discovery,parameters 带 excluded_role_ids=遮蔽集,
     使被遮蔽岗位在覆盖率、novelty 与最近岗位分类全链路中被当作不存在;
  3. 检查被遮蔽岗位能否作为高分候选被重新发现:Recall@K(10/25/50/100)、
     被遮蔽岗位的候选排名分布、候选与被遮蔽岗位的技术集合 Jaccard、
     随机排序基线(同种子)。

边界:本脚本只封装调用与测量,不改动 discovery 的评分、分类与去重逻辑。
冻结要求:遮蔽比例、随机种子、算法版本、输入快照哈希、参数快照全部落入
manifest 与报告头部;遮蔽集由(合格岗位集合 + mask_ratio + seed)纯函数导出,
禁止任何手工名单。默认 dry-run,显式 --execute 才真正执行推演。

正式执行前提:任务组 5(下游重新标定)完成之后(窗口 D)。在抽取质量修复前
跑出的 Recall 数字没有研究意义。
"""

import argparse
import hashlib
import json
import random
import re
import statistics
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.clustering.models import (
    JobRole,
    JobRoleVersion,
    JobRoleVersionRequirement,
)
from app.modules.discovery.models import (
    CandidateTechnology,
    DiscoveryRun,
    EmergingRoleCandidate,
)
from app.modules.discovery.service import DEFAULT_PARAMETERS, run_discovery

PROTOCOL_VERSION = "holdout_rediscovery_v1"
RECALL_KS = (10, 25, 50, 100)
DEFAULT_MASK_RATIO = 0.2
DEFAULT_JACCARD_THRESHOLD = 0.5

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "reports"
DEFAULT_TEMPLATE_PATH = DEFAULT_OUTPUT_DIR / "holdout实验报告模板.md"

FROZEN_KEYS = (
    "protocol_version",
    "run_code",
    "already_completed",
    "target_date",
    "mask_ratio",
    "seed",
    "min_technology_count",
    "jaccard_threshold",
    "recall_ks",
    "algorithm_version",
    "input_snapshot_hash",
    "parameter_snapshot",
    "eligible_role_ids",
    "masked_role_ids",
    "new_candidate_count",
)


class HoldoutExperimentError(ValueError):
    """A user-correctable holdout experiment error."""


@dataclass(frozen=True)
class CandidateProfile:
    """参与排名的候选:run_discovery 的产出,本脚本只读取。"""

    candidate_code: str
    score: float
    technology_ids: frozenset[int]
    classification_code: str


@dataclass(frozen=True)
class RoleMatch:
    """一个被遮蔽岗位在全量候选中的最佳匹配。"""

    role_id: int
    role_name: str
    technology_count: int
    best_candidate_code: str | None
    best_jaccard: float
    best_rank: int | None
    matched: bool


def eligible_mask_roles(
    db: Session, target_date: date, min_technology_count: int
) -> dict[int, tuple[str, frozenset[int]]]:
    """返回有资格进入遮蔽采样池的岗位:{role_id: (岗位名, 技术词集合)}。

    口径与推演侧的岗位画像一致:岗位活跃、版本已审批且在 target_date 生效;
    存在技术词数 >= min_technology_count 的生效版本即视为参与最近岗位比较,
    技术集合取其中 version_no 最大的版本(与画像中实际参与比较的版本对应)。
    """
    rows = list(
        db.execute(
            select(JobRoleVersion, JobRole)
            .join(JobRole, JobRole.job_role_id == JobRoleVersion.job_role_id)
            .where(
                JobRole.lifecycle_status_code == "active",
                JobRoleVersion.approval_status_code == "approved",
                JobRoleVersion.valid_from <= target_date,
                or_(
                    JobRoleVersion.valid_to.is_(None),
                    JobRoleVersion.valid_to >= target_date,
                ),
            )
        )
    )
    if not rows:
        return {}
    version_ids = sorted({version.job_role_version_id for version, _ in rows})
    tech_by_version: dict[int, set[int]] = {version_id: set() for version_id in version_ids}
    for version_id, technology_id in db.execute(
        select(
            JobRoleVersionRequirement.job_role_version_id,
            JobRoleVersionRequirement.technology_node_id,
        ).where(JobRoleVersionRequirement.job_role_version_id.in_(version_ids))
    ):
        tech_by_version[version_id].add(technology_id)
    versions_by_role: dict[int, list[tuple[JobRoleVersion, str, frozenset[int]]]] = {}
    for version, role in rows:
        technologies = frozenset(tech_by_version[version.job_role_version_id])
        versions_by_role.setdefault(version.job_role_id, []).append(
            (version, role.canonical_name, technologies)
        )
    eligible: dict[int, tuple[str, frozenset[int]]] = {}
    for role_id, versions in versions_by_role.items():
        qualifying = [item for item in versions if len(item[2]) >= min_technology_count]
        if not qualifying:
            continue
        version, name, technologies = max(qualifying, key=lambda item: item[0].version_no)
        eligible[role_id] = (name, technologies)
    return eligible


def build_mask_set(eligible_role_ids: Iterable[int], mask_ratio: float, seed: int) -> list[int]:
    """遮蔽集 = (合格岗位集合, mask_ratio, seed) 的确定性纯函数。

    采样数量按四舍五入取整;同 seed 同输入必然得到同一集合,与传入顺序无关。
    """
    if not 0 < mask_ratio <= 1:
        raise HoldoutExperimentError("mask_ratio 必须在 (0, 1] 区间内")
    ordered = sorted(eligible_role_ids)
    if not ordered:
        raise HoldoutExperimentError("不存在满足技术词资格线的正式岗位,无法构造遮蔽集")
    mask_count = int(len(ordered) * mask_ratio + 0.5)
    if mask_count == 0:
        raise HoldoutExperimentError(
            f"遮蔽岗位数为 0(合格岗位 {len(ordered)} 个 × 比例 {mask_ratio}),"
            "请调大 mask_ratio 或检查资格岗位数量"
        )
    return sorted(random.Random(seed).sample(ordered, min(mask_count, len(ordered))))


def load_run_candidates(db: Session, run_code: str) -> list[CandidateProfile]:
    """读取本次运行实际提出的候选,按分数降序(同分按候选码)排名。

    候选按 candidate_key 去重,已存在的行会被就地刷新并保留首次提出的
    discovery_run_id,因此不能按 discovery_run_id 过滤,而以机械事实卡中的
    last_seen_run_code 判定该候选在本次运行中出现过。
    """
    rows = [
        candidate
        for candidate in db.scalars(select(EmergingRoleCandidate))
        if (candidate.mechanical_card_json or {}).get("last_seen_run_code") == run_code
    ]
    if not rows:
        return []
    technology_map: dict[int, set[int]] = {
        candidate.emerging_role_candidate_id: set() for candidate in rows
    }
    for candidate_id, technology_id in db.execute(
        select(
            CandidateTechnology.emerging_role_candidate_id,
            CandidateTechnology.technology_node_id,
        ).where(CandidateTechnology.emerging_role_candidate_id.in_(list(technology_map)))
    ):
        technology_map[candidate_id].add(technology_id)
    profiles = [
        CandidateProfile(
            candidate_code=candidate.candidate_code,
            score=float(candidate.candidate_score),
            technology_ids=frozenset(technology_map[candidate.emerging_role_candidate_id]),
            classification_code=candidate.classification_code,
        )
        for candidate in rows
    ]
    return sorted(profiles, key=lambda item: (-item.score, item.candidate_code))


def jaccard(left: frozenset[int], right: frozenset[int]) -> float:
    """技术集合的对称 Jaccard 重合度;空并集(双方皆空)定义为 0。"""
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _recall_curve(rows: list[tuple[int | None, bool]], ks) -> dict[str, float]:
    """rows = [(排名或 None, 是否达到 Jaccard 门槛)];分母为全部被遮蔽岗位。"""
    total = len(rows)
    return {
        str(k): (
            sum(1 for rank, matched in rows if matched and rank is not None and rank <= k) / total
            if total
            else 0.0
        )
        for k in ks
    }


def evaluate(
    ranked_candidates: list[CandidateProfile],
    masked_roles: dict[int, tuple[str, frozenset[int]]],
    *,
    jaccard_threshold: float,
    seed: int,
    ks: tuple[int, ...] = RECALL_KS,
) -> dict:
    """纯函数指标计算:不触库,可用已知排名的假候选直接验证数值。"""
    matches: list[RoleMatch] = []
    for role_id in sorted(masked_roles):
        role_name, role_technologies = masked_roles[role_id]
        best_jaccard = 0.0
        best_rank: int | None = None
        best_code: str | None = None
        for rank, candidate in enumerate(ranked_candidates, start=1):
            overlap = jaccard(role_technologies, candidate.technology_ids)
            if overlap > best_jaccard:
                best_jaccard = overlap
                best_rank = rank
                best_code = candidate.candidate_code
        matches.append(
            RoleMatch(
                role_id=role_id,
                role_name=role_name,
                technology_count=len(role_technologies),
                best_candidate_code=best_code,
                best_jaccard=best_jaccard,
                best_rank=best_rank,
                matched=best_jaccard >= jaccard_threshold,
            )
        )
    recall = _recall_curve([(match.best_rank, match.matched) for match in matches], ks)
    # 随机排序基线:同一候选集合、同一最佳匹配判定,只把排名换成同种子洗牌。
    shuffled = list(ranked_candidates)
    random.Random(seed).shuffle(shuffled)
    position = {candidate.candidate_code: index + 1 for index, candidate in enumerate(shuffled)}
    baseline = _recall_curve(
        [
            (position.get(match.best_candidate_code) if match.matched else None, match.matched)
            for match in matches
        ],
        ks,
    )
    matched_ranks = [match.best_rank for match in matches if match.matched]
    jaccards = [match.best_jaccard for match in matches]
    return {
        "masked_role_count": len(matches),
        "candidate_count": len(ranked_candidates),
        "recall_ks": list(ks),
        "recall_at_k": recall,
        "random_baseline_recall_at_k": baseline,
        "matched_role_count": len(matched_ranks),
        "unmatched_role_count": len(matches) - len(matched_ranks),
        "rank_summary": {
            "min": min(matched_ranks) if matched_ranks else None,
            "median": statistics.median(matched_ranks) if matched_ranks else None,
            "max": max(matched_ranks) if matched_ranks else None,
            "no_match_count": len(matches) - len(matched_ranks),
        },
        "jaccard_summary": {
            "mean": sum(jaccards) / len(jaccards) if jaccards else None,
            "median": statistics.median(jaccards) if jaccards else None,
            "min": min(jaccards) if jaccards else None,
            "max": max(jaccards) if jaccards else None,
        },
        "per_masked_role": [
            {
                "role_id": match.role_id,
                "role_name": match.role_name,
                "technology_count": match.technology_count,
                "best_candidate_code": match.best_candidate_code,
                "best_jaccard": match.best_jaccard,
                "best_rank": match.best_rank,
                "matched": match.matched,
            }
            for match in matches
        ],
    }


def run_experiment(
    db: Session,
    *,
    target_date: date,
    mask_ratio: float = DEFAULT_MASK_RATIO,
    seed: int,
    jaccard_threshold: float = DEFAULT_JACCARD_THRESHOLD,
    min_technology_count: int | None = None,
) -> dict:
    """执行一次完整实验:采样遮蔽集 -> 遮蔽状态下推演 -> 读取并测量。

    返回的字典即实验记录;除 metrics 外的字段构成 manifest 审计负载。
    """
    if min_technology_count is None:
        min_technology_count = int(DEFAULT_PARAMETERS["min_role_technology_count"])
    eligible = eligible_mask_roles(db, target_date, min_technology_count)
    masked_ids = build_mask_set(sorted(eligible), mask_ratio, seed)
    result = run_discovery(
        db,
        mode_code="automatic",
        target_date=target_date,
        parameters={"excluded_role_ids": masked_ids},
    )
    run = db.scalar(select(DiscoveryRun).where(DiscoveryRun.run_code == result.run_code))
    if run is None:
        raise HoldoutExperimentError("推演运行记录缺失,无法冻结实验字段")
    ranked = load_run_candidates(db, result.run_code)
    masked_roles = {role_id: eligible[role_id] for role_id in masked_ids}
    metrics = evaluate(
        ranked,
        masked_roles,
        jaccard_threshold=jaccard_threshold,
        seed=seed,
    )
    return {
        "protocol_version": PROTOCOL_VERSION,
        "run_code": run.run_code,
        "already_completed": result.already_completed,
        "target_date": target_date.isoformat(),
        "mask_ratio": mask_ratio,
        "seed": seed,
        "min_technology_count": min_technology_count,
        "jaccard_threshold": jaccard_threshold,
        "recall_ks": list(RECALL_KS),
        "algorithm_version": run.algorithm_version,
        "input_snapshot_hash": run.input_snapshot_hash,
        "parameter_snapshot": run.parameter_json,
        "eligible_role_ids": sorted(eligible),
        "masked_role_ids": masked_ids,
        "new_candidate_count": result.candidate_count,
        "metrics": metrics,
    }


def _sha256_json(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def build_manifest(experiment: dict) -> dict:
    """manifest = 实验记录去掉 metrics 后加自校验 sha256。"""
    body = {key: value for key, value in experiment.items() if key != "metrics"}
    body["manifest_sha256"] = _sha256_json(body)
    return body


def build_metrics_file(experiment: dict) -> dict:
    return {
        "frozen": {key: experiment[key] for key in FROZEN_KEYS},
        "metrics": experiment["metrics"],
    }


def _recall_table(metrics: dict) -> str:
    lines = [
        "| K | Recall@K | 随机排序基线 | 提升 |",
        "| ---: | ---: | ---: | ---: |",
    ]
    for k in metrics["recall_ks"]:
        model = metrics["recall_at_k"][str(k)]
        baseline = metrics["random_baseline_recall_at_k"][str(k)]
        lines.append(f"| {k} | {model:.4f} | {baseline:.4f} | {model - baseline:+.4f} |")
    return "\n".join(lines)


def _per_role_table(metrics: dict) -> str:
    lines = [
        "| 岗位ID | 岗位名 | 技术词数 | 最佳候选 | Jaccard | 排名 | 达到门槛 |",
        "| ---: | --- | ---: | --- | ---: | ---: | --- |",
    ]
    for row in metrics["per_masked_role"]:
        rank = "—" if row["best_rank"] is None else str(row["best_rank"])
        code = row["best_candidate_code"] or "—"
        lines.append(
            f"| {row['role_id']} | {row['role_name']} | {row['technology_count']} "
            f"| {code} | {row['best_jaccard']:.4f} | {rank} |"
            f" {'是' if row['matched'] else '否'} |"
        )
    return "\n".join(lines)


def _summary_line(
    values: dict[str, float | int | None], labels: tuple[tuple[str, str], ...]
) -> str:
    parts = []
    for label, key in labels:
        value = values[key]
        if value is None:
            parts.append(f"{label} —")
        elif isinstance(value, float):
            parts.append(f"{label} {value:.4f}")
        else:
            parts.append(f"{label} {value}")
    return " · ".join(parts)


def render_report(template_text: str, experiment: dict) -> str:
    """按 docs/reports/holdout实验报告模板.md 渲染报告;不允许残留占位符。

    渲染是纯函数:同一 experiment 得到逐字节相同的报告(不含任何时间戳)。
    """
    metrics = experiment["metrics"]
    substitutions = {
        "protocol_version": experiment["protocol_version"],
        "run_code": experiment["run_code"],
        "already_completed": (
            "是(命中重放缓存,复用既有运行)" if experiment["already_completed"] else "否"
        ),
        "target_date": experiment["target_date"],
        "mask_ratio": str(experiment["mask_ratio"]),
        "seed": str(experiment["seed"]),
        "min_technology_count": str(experiment["min_technology_count"]),
        "jaccard_threshold": str(experiment["jaccard_threshold"]),
        "algorithm_version": experiment["algorithm_version"],
        "input_snapshot_hash": experiment["input_snapshot_hash"],
        "eligible_role_count": str(len(experiment["eligible_role_ids"])),
        "masked_role_count": str(metrics["masked_role_count"]),
        "candidate_count": str(metrics["candidate_count"]),
        "parameters_json": json.dumps(
            experiment["parameter_snapshot"], ensure_ascii=False, indent=2
        ),
        "recall_table": _recall_table(metrics),
        "per_role_table": _per_role_table(metrics),
        "rank_summary": _summary_line(
            metrics["rank_summary"],
            (("最小", "min"), ("中位数", "median"), ("最大", "max"), ("无匹配", "no_match_count")),
        ),
        "jaccard_summary": _summary_line(
            metrics["jaccard_summary"],
            (("均值", "mean"), ("中位数", "median"), ("最小", "min"), ("最大", "max")),
        ),
    }
    rendered = template_text
    for key, value in substitutions.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    leftovers = sorted(set(re.findall(r"\{\{[^}]*\}\}", rendered)))
    if leftovers:
        raise HoldoutExperimentError(f"报告模板存在未替换占位符: {leftovers}")
    return rendered


def write_outputs(output_dir: Path, template_path: Path, experiment: dict) -> dict[str, Path]:
    """落盘 manifest / metrics JSON 与按模板渲染的报告,全部确定性内容。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    run_code = experiment["run_code"]
    manifest_path = output_dir / f"holdout_manifest_{run_code}.json"
    metrics_path = output_dir / f"holdout_metrics_{run_code}.json"
    report_path = output_dir / f"holdout实验报告_{run_code}.md"
    manifest_path.write_text(
        json.dumps(build_manifest(experiment), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    metrics_path.write_text(
        json.dumps(build_metrics_file(experiment), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    report_path.write_text(
        render_report(template_path.read_text(encoding="utf-8"), experiment),
        encoding="utf-8",
    )
    return {
        "manifest": manifest_path,
        "metrics": metrics_path,
        "report": report_path,
    }


def _build_plan(args: argparse.Namespace, eligible: dict, masked_ids: list[int]) -> dict:
    return {
        "mode": "dry-run" if not args.execute else "execute",
        "protocol_version": PROTOCOL_VERSION,
        "target_date": args.target_date.isoformat(),
        "mask_ratio": args.mask_ratio,
        "seed": args.seed,
        "min_technology_count": args.min_technology_count,
        "jaccard_threshold": args.jaccard_threshold,
        "eligible_role_count": len(eligible),
        "masked_role_ids": masked_ids,
        "masked_role_count": len(masked_ids),
        "invoke": (
            "run_discovery(mode_code='automatic', "
            "parameters={'excluded_role_ids': masked_role_ids})"
        ),
    }


def main(argv: list[str] | None = None, session_factory=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "留出重发现实验:遮蔽部分正式岗位,在遮蔽状态下跑新岗位推演并测量重发现率。"
            "默认 dry-run 只打印计划;显式 --execute 才执行推演并写报告。"
        )
    )
    parser.add_argument("--target-date", type=date.fromisoformat, required=True)
    parser.add_argument("--mask-ratio", type=float, default=DEFAULT_MASK_RATIO)
    parser.add_argument(
        "--seed",
        type=int,
        required=True,
        help="随机种子,与 mask_ratio 一起冻结进实验记录与 manifest",
    )
    parser.add_argument(
        "--jaccard-threshold",
        type=float,
        default=DEFAULT_JACCARD_THRESHOLD,
        help="候选与被遮蔽岗位技术集合 Jaccard 达到该值才计为重新发现",
    )
    parser.add_argument(
        "--min-technology-count",
        type=int,
        default=None,
        help="遮蔽资格线;默认取推演参数 min_role_technology_count,保持两侧口径一致",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE_PATH)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="确认执行:将调用 run_discovery 并写入正式实验记录(窗口 D 之后才可用)",
    )
    args = parser.parse_args(argv)
    args.min_technology_count = (
        args.min_technology_count
        if args.min_technology_count is not None
        else int(DEFAULT_PARAMETERS["min_role_technology_count"])
    )
    if session_factory is None:
        from app.db.session import SessionLocal

        session_factory = SessionLocal
    with session_factory() as session:
        eligible = eligible_mask_roles(session, args.target_date, args.min_technology_count)
        masked_ids = build_mask_set(sorted(eligible), args.mask_ratio, args.seed)
        if not args.execute:
            plan = _build_plan(args, eligible, masked_ids)
            plan["note"] = "dry-run:未调用 run_discovery,未写入任何数据;加 --execute 才执行"
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0
        experiment = run_experiment(
            session,
            target_date=args.target_date,
            mask_ratio=args.mask_ratio,
            seed=args.seed,
            jaccard_threshold=args.jaccard_threshold,
            min_technology_count=args.min_technology_count,
        )
    paths = write_outputs(args.output_dir, args.template, experiment)
    print(
        json.dumps(
            {
                "run_code": experiment["run_code"],
                "already_completed": experiment["already_completed"],
                "algorithm_version": experiment["algorithm_version"],
                "input_snapshot_hash": experiment["input_snapshot_hash"],
                "recall_at_k": experiment["metrics"]["recall_at_k"],
                "outputs": {key: str(path) for key, path in paths.items()},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
