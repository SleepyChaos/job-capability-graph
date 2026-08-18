"""把新代码补标注合并进标注包（窗口 C-7 全口径评估用）。

词表升版新增了 L3 技术点，但标注是在旧代码空间里做的——新代码在真值侧永远缺席，
直接算 P/R 会把新技术点的每一次正确命中都记成误报。补标注文件只对新代码追加期望，
**v1.1 代码上的原判定逐字不动**，两半合起来才是 v1.2 代码空间下的完整真值。

补标注与被评估系统不独立（见扩展文件里的 caveat），产出的全口径数字偏乐观，
跨版本对比应以受限口径为准（`evaluate_extraction_quality.py --restrict-codes`）。

用法：
    python tools/apply_annotation_extension.py \
        --package data/annotation/annotator_C.v1_2.json \
        --extension docs/reports/annotation_package/annotator_C.v1_2_extension.json \
        --out data/annotation/annotator_C.v1_2.extended.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将新代码补标注合并进标注包。")
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--extension", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    package = json.loads(args.package.read_text(encoding="utf-8"))
    extension = json.loads(args.extension.read_text(encoding="utf-8"))

    by_sample: dict[str, set[str]] = {}
    for code, sample_ids in extension["additions"].items():
        for sample_id in sample_ids:
            by_sample.setdefault(sample_id, set()).add(code)

    known = {sample["sample_id"] for sample in package["samples"]}
    unknown = sorted(set(by_sample) - known)
    if unknown:
        raise SystemExit(f"补标注引用了不存在的样本：{unknown}")

    added = 0
    for sample in package["samples"]:
        extra = by_sample.get(sample["sample_id"])
        if not extra:
            continue
        existing = set(sample["expected_l3_codes"])
        overlap = existing & extra
        if overlap:
            raise SystemExit(
                f"补标注与原标注冲突（{sample['sample_id']} 已有 {sorted(overlap)}）"
                "：补标注只应覆盖新版新增的代码"
            )
        sample["expected_l3_codes"] = sorted(existing | extra)
        added += len(extra)

    package["annotation_extension_id"] = extension["extension_id"]
    package["annotation_caveat"] = (
        f"{package.get('annotation_caveat', '')} 另含新代码补标注：{extension['caveat']}"
    ).strip()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "out": str(args.out),
                "extension_id": extension["extension_id"],
                "added_expectation_count": added,
                "touched_sample_count": len(by_sample),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
