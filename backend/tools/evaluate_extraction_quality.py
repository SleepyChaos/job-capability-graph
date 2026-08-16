"""窗口 A-1 子任务 1.3b:标注 vs 实际抽取的对照评估。

输入:标注包 JSON(jd_annotation_batch_001 的填写版,字段见同目录《标注说明.md》):
每份样本含 `expected_l3_codes`(人工认定应抽出的 L3 代码)与 `current_extraction`
(冻结快照,含 status)。

指标口径:
- 预测侧(实际抽取)默认只取 `status == accepted` 的 L3;`--include-review`
  时并入 needs_review(口径变化会显著改变结果,报告必须注明用了哪种)
- 真值侧为 `expected_l3_codes`
- 样本级 P/R/F1 集合到 JD 上:TP = |期望 ∩ 预测|,FP = |预测 − 期望|,
  FN = |期望 − 预测|;分层报告按 role_type 与 primary_domain 聚合(micro)
- 置信区间:JD 级 bootstrap 重采样(默认 B=2000,种子固定,确定性)
- 双人标注:可传 --package 两次(annotator A/B),脚本另报两人逐 JD 的
  集合 Jaccard 一致率;有裁决版 gold 时以 gold 为准

自测:`--self-test` 用脚本内嵌的合成标注包验证指标正确性(预期精确值硬编码)。

用法(在 backend 目录):
    python tools/evaluate_extraction_quality.py --package <标注包.json> [--include-review]
    python tools/evaluate_extraction_quality.py --self-test
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

ROLE_LABEL = {
    "embodied_algo": "具身算法岗",
    "hardware": "硬件岗",
    "engineering": "工程岗",
    "non_technical": "非技术岗",
}


def predicted_codes(sample: dict, include_review: bool) -> set[str]:
    statuses = {"accepted"} | ({"needs_review"} if include_review else set())
    return {
        row["technology_code"] for row in sample["current_extraction"] if row["status"] in statuses
    }


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def confusion(samples: list[dict], include_review: bool) -> tuple[int, int, int]:
    tp = fp = fn = 0
    for sample in samples:
        expected = set(sample["expected_l3_codes"])
        predicted = predicted_codes(sample, include_review)
        tp += len(expected & predicted)
        fp += len(predicted - expected)
        fn += len(expected - predicted)
    return tp, fp, fn


def bootstrap_ci(
    samples: list[dict],
    include_review: bool,
    repeats: int,
    seed: int,
) -> dict[str, tuple[float, float]]:
    rng = random.Random(seed)
    stats: dict[str, list[float]] = {"precision": [], "recall": [], "f1": []}
    for _ in range(repeats):
        draw = [samples[rng.randrange(len(samples))] for _ in range(len(samples))]
        p, r, f = prf(*confusion(draw, include_review))
        stats["precision"].append(p)
        stats["recall"].append(r)
        stats["f1"].append(f)
    ci: dict[str, tuple[float, float]] = {}
    for key, values in stats.items():
        ordered = sorted(values)
        ci[key] = (ordered[int(0.025 * len(ordered))], ordered[int(0.975 * len(ordered)) - 1])
    return ci


def evaluate(samples: list[dict], include_review: bool, repeats: int, seed: int) -> list[str]:
    lines: list[str] = []
    tp, fp, fn = confusion(samples, include_review)
    p, r, f = prf(tp, fp, fn)
    ci = bootstrap_ci(samples, include_review, repeats, seed)
    lines.append(
        f"| 总体(micro, {len(samples)} 份 JD) | {tp} | {fp} | {fn} "
        f"| {p:.3f} [{ci['precision'][0]:.3f}, {ci['precision'][1]:.3f}] "
        f"| {r:.3f} [{ci['recall'][0]:.3f}, {ci['recall'][1]:.3f}] "
        f"| {f:.3f} [{ci['f1'][0]:.3f}, {ci['f1'][1]:.3f}] |"
    )
    for field, label in (("role_type", "岗位类型"), ("primary_domain", "T 域")):
        groups: dict[str, list[dict]] = defaultdict(list)
        for sample in samples:
            key = sample.get(field) or "未填写"
            if field == "role_type":
                key = ROLE_LABEL.get(key, key)
            groups[key].append(sample)
        for key in sorted(groups):
            rows = groups[key]
            gtp, gfp, gfn = confusion(rows, include_review)
            gp, gr, gf = prf(gtp, gfp, gfn)
            lines.append(
                f"| {label}={key}(n={len(rows)}) | {gtp} | {gfp} | {gfn} "
                f"| {gp:.3f} | {gr:.3f} | {gf:.3f} |"
            )
    return lines


def agreement_jaccard(pkg_a: dict, pkg_b: dict) -> float:
    by_id_b = {s["sample_id"]: set(s["expected_l3_codes"]) for s in pkg_b["samples"]}
    scores = []
    for sample in pkg_a["samples"]:
        other = by_id_b.get(sample["sample_id"], set())
        mine = set(sample["expected_l3_codes"])
        union = mine | other
        scores.append(len(mine & other) / len(union) if union else 1.0)
    return sum(scores) / len(scores) if scores else 0.0


def self_test() -> None:
    """合成标注包:3 份样本,预期 micro TP=1/FP=2/FN=2(P=R=F1=1/3,硬编码核对)。"""

    def sample(sid, role, domain, expected, extracted):
        return {
            "sample_id": sid,
            "role_type": role,
            "primary_domain": domain,
            "expected_l3_codes": expected,
            "current_extraction": [
                {"technology_code": code, "technology_name": code, "status": status}
                for code, status in extracted
            ],
        }

    pkg = {
        "samples": [
            sample("s1", "embodied_algo", "T1", ["A", "B"], [("A", "accepted"), ("C", "accepted")]),
            sample("s2", "non_technical", "T7", [], [("D", "accepted")]),
            sample("s3", "hardware", "T3", ["B"], []),
        ]
    }
    tp, fp, fn = confusion(pkg["samples"], include_review=False)
    assert (tp, fp, fn) == (1, 2, 2), (tp, fp, fn)
    p, r, f = prf(tp, fp, fn)
    assert abs(p - 1 / 3) < 1e-12 and abs(r - 1 / 3) < 1e-12, (p, r)
    assert abs(f - 2 * p * r / (p + r)) < 1e-12
    # include-review 口径:s2 的 D 为 accepted 不变;s1 无 review 行 -> 数字不变
    tp2, fp2, fn2 = confusion(pkg["samples"], include_review=True)
    assert (tp2, fp2, fn2) == (1, 2, 2)
    pkg["samples"][0]["current_extraction"].append(
        {"technology_code": "B", "technology_name": "B", "status": "needs_review"}
    )
    tp3, fp3, fn3 = confusion(pkg["samples"], include_review=True)
    assert (tp3, fp3, fn3) == (2, 2, 1), (tp3, fp3, fn3)
    tp4, fp4, fn4 = confusion(pkg["samples"], include_review=False)
    assert (tp4, fp4, fn4) == (1, 2, 2), "include_review=False 不应受 needs_review 影响"
    ci = bootstrap_ci(pkg["samples"], include_review=False, repeats=200, seed=42)
    assert all(lo <= hi for lo, hi in ci.values())
    jac = agreement_jaccard(pkg, {**pkg, "samples": pkg["samples"]})
    assert jac == 1.0
    print("self-test 通过:指标计算/口径切换/bootstrap CI/双人一致率均符合预期")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package", type=Path, action="append", help="标注包 JSON(可传两个做双人对比)"
    )
    parser.add_argument(
        "--include-review", action="store_true", help="预测侧并入 needs_review(默认仅 accepted)"
    )
    parser.add_argument("--bootstrap-repeats", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260816)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if not args.package:
        parser.error("需要 --package 或 --self-test")

    packages = []
    for path in args.package:
        pkg = json.loads(path.read_text(encoding="utf-8"))
        pending = [
            s
            for s in pkg["samples"]
            if not s.get("expected_l3_codes") and s.get("role_type") is None
        ]
        if pending:
            raise SystemExit(
                f"{path.name} 有 {len(pending)} 份样本未标注(expected_l3_codes 与 role_type 均为空)"
            )
        packages.append((path, pkg))

    caliber = "accepted+needs_review" if args.include_review else "仅 accepted"
    print("# 抽取质量评估(标注对照)\n")
    print(f"- 标注包:{', '.join(str(p) for p, _ in packages)}")
    print(f"- 预测侧口径:{caliber};run {packages[0][1].get('parse_run_code', '?')},无 LLM 回写")
    annotated = [s for s in packages[0][1]["samples"]]
    single = len(packages) == 1
    print(f"- 标注方式:{'单人标注' if single else '双人标注(以下为首包,另报两人一致率)'}\n")
    print("| 分层 | TP | FP | FN | Precision [95%CI] | Recall [95%CI] | F1 [95%CI] |")
    print("| --- | ---: | ---: | ---: | --- | --- | --- |")
    for line in evaluate(annotated, args.include_review, args.bootstrap_repeats, args.seed):
        print(line)
    if not single:
        jac = agreement_jaccard(packages[0][1], packages[1][1])
        print(f"\n双人逐 JD 集合 Jaccard 一致率(均值):{jac:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
