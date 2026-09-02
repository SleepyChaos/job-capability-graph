"""Build the independent JD-to-role inference result without changing the live graph."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.modules.graph.role_inference import infer_roles

DEFAULT_GRAPH = ROOT / "data/processed/job_graph/job-ecosystem-graph.json"
DEFAULT_TECH = ROOT / "data/processed/job_graph/knowledge-inference.json"
DEFAULT_OUTPUT = ROOT / "data/processed/job_graph/role-inference.json"
DEFAULT_REPORT = ROOT / "data/processed/job_graph/role-inference-report.md"


def _load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build(graph_path: Path, tech_path: Path, output_path: Path, report_path: Path) -> dict:
    result = infer_roles(_load(graph_path), _load(tech_path))
    result["metadata"]["generatedAt"] = datetime.now(UTC).isoformat()
    result["metadata"]["sourceGraph"] = str(graph_path.relative_to(ROOT))
    result["metadata"]["technicalInference"] = str(tech_path.relative_to(ROOT))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)

    audit = result["audit"]
    sample = next((x for x in result["jobRoleInferences"] if x["publishable"]), result["jobRoleInferences"][0])
    best = sample["standardRole"]["result"] or {}
    lines = [
        "# 独立岗位推理构建报告", "",
        "> 本结果不覆盖当前图谱与历史 Excel 映射。历史映射仅保存在 `legacyMapping` 中作为参考。", "",
        "## 构建结果", "",
        f"- 处理 JD：{audit['jobCount']:,} 条",
        f"- 状态分布：{json.dumps(audit['statusDistribution'], ensure_ascii=False)}",
        f"- 形成画像的标准岗位：{audit['confirmedProfileCount']} 个",
        f"- 输出文件：`{output_path.relative_to(ROOT)}`", "",
        "## 置信闸门", "",
        "- `confirmed`：综合分达到 0.74、领先第二候选至少 0.08，且至少有两个证据通道；仅此状态标记为可发布。",
        "- `candidate`：达到候选阈值，但不自动进入正式标准岗位关系。",
        "- `review_required`：证据不足或候选接近，交由人工审核。",
        "- `new_role_candidate`：现有标准岗位均无法合理解释，进入新岗位候选池。", "",
        "## 示例", "",
        f"- JD：{sample['jdId']} / {sample['title']}",
        f"- 历史岗位：{sample['legacyMapping']['standardRoleName'] or '无'}",
        f"- 新推理岗位：{best.get('roleName') or '无'}",
        f"- 综合分：{best.get('score', 0)}；差值：{sample['standardRole']['margin']}；状态：{sample['standardRole']['status']}",
        f"- 分项：{json.dumps(best.get('componentScores', {}), ensure_ascii=False)}", "",
        "## 画像证据规则", "",
        "每个画像点仅记录实际抽取出该点的 JD。`supportCount` 为去重后的支持 JD 数，`coverage` 的分母为该标准岗位通过闸门的 JD 总数；单条 JD 支持的点保留在候选画像中，不作为共性画像发布。", "",
        "## 当前边界", "",
        "岗位簇候选仍使用历史岗位簇作为一个弱提示，但方向、类别由最佳候选岗位簇的上位层级推导；岗位判断采用可解释规则和技术链证据，尚未使用人工金标准做独立准确率评测。",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    parser.add_argument("--technical-inference", type=Path, default=DEFAULT_TECH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    result = build(args.graph, args.technical_inference, args.output, args.report)
    print(json.dumps(result["audit"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
