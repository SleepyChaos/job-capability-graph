"""Build lightweight derived relations for the static job knowledge graph."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from app.modules.graph.inference import infer_graph_relations


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "data" / "processed" / "job_graph" / "job-ecosystem-graph.json"
DEFAULT_OUTPUT = ROOT / "data" / "processed" / "job_graph" / "knowledge-inference.json"
DEFAULT_REPORT = ROOT / "data" / "processed" / "job_graph" / "knowledge-inference-report.md"


def _write_json_atomic(path: Path, payload: dict[str, Any], *, compact: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":") if compact else None,
        indent=None if compact else 2,
    )
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)


def _write_report(path: Path, payload: dict[str, Any], source: Path, output: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = payload["metadata"]
    examples = sorted(
        payload["standardRoleTechnologyRelations"],
        key=lambda item: (-item["supportCount"], item["sourceId"], item["targetId"]),
    )[:10]
    example_rows = "\n".join(
        (
            "| {sourceName} | {targetName} | {targetLevel} | {supportCount} | "
            "{roleJdCount} | {coverage:.2%} |"
        ).format(**item)
        for item in examples
        if item["coverage"] is not None
    )
    report = f"""# 轻量知识推理构建报告

> 源图谱：`{source.name}`  
> 派生结果：`{output.name}`  
> 生成时间：{metadata['generatedAt']}

## 规则与结果

- R1 技术层级继承关系：{metadata['r1RelationCount']:,} 条
- R2 标准岗位—技术关系：{metadata['r2RelationCount']:,} 条
- 直接获得L4技术关系的JD：{metadata['directTechnologyJobCount']:,} 条
- 数据警告：{metadata['warningCount']:,} 条

推理结果与原始事实分开保存。覆盖率表示支持JD数占该标准岗位全部JD的比例，不代表准确率，也不直接表示必备技能。

## 支持JD数较多的派生关系示例

| 标准岗位 | 技术 | 层级 | 支持JD数 | 岗位JD总数 | 覆盖率 |
| --- | --- | --- | ---: | ---: | ---: |
{example_rows}
"""
    path.write_text(report, encoding="utf-8")


def build(source: Path, output: Path, report: Path, *, compact: bool = True) -> dict[str, Any]:
    source_bytes = source.read_bytes()
    graph = json.loads(source_bytes.decode("utf-8"))
    payload = infer_graph_relations(
        graph,
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
    )
    _write_json_atomic(output, payload, compact=compact)
    _write_report(report, payload, source, output)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate evidence-preserving R1/R2 relations from the static job graph."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--pretty", action="store_true", help="write indented JSON")
    args = parser.parse_args()

    payload = build(args.source, args.output, args.report, compact=not args.pretty)
    print(json.dumps(payload["metadata"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
