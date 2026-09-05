"""把覆盖率 HTML 报告中被裁模块的逐行页替换成说明页。

coverage.py 的 HTML 报告会逐行内嵌被测源码。交付源码包裁掉了 discovery、clustering、
extraction 三个模块的实现，但覆盖率报告里这些文件的完整源码仍以 HTML 形式存在——
浏览器打开就能逐行读，另存去掉行号即可还原成可运行的 .py。不处理的话源码裁剪等于没做。

处理方式不是删文件：`index.html` 有指向它们的链接，删了会变成断链，看起来像报告损坏。
改成替换为说明页，保留链接可达，点进去看到的是「为什么这里没有逐行标注」。

覆盖率数字不受影响：汇总页 `index.html` 上每个文件的语句数、未覆盖数与百分比照旧，
总计 78.79% 也照旧——那是在完整代码上跑出来的，本脚本只动展示层。

裁剪范围与 build_redacted_source_package.py 共用同一份配置，避免两边漂移。

用法：
    python scripts/redact_coverage_report.py
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from build_redacted_source_package import KEEP_DECLARATIVE, REDACT_DIRS  # noqa: E402

COVERAGE = REPO / "交付材料-单元测试" / "coverage"

# coverage 报告里的路径以 backend/ 为根（pyproject 的 source = ["app"]），
# 裁剪清单里的路径以仓库为根，比对前去掉这层前缀。
PREFIX = "backend/"

# 只认路径本身：coverage 原始页的标题是 `Coverage for <path>: 98%`，而本脚本
# 早期产出的说明页曾在标题后缀过中文，宽松匹配才能对已处理过的页面重复执行
# （否则旧措辞会永远留在包里）。
TITLE_RE = re.compile(r"<title>Coverage for ([^\s:<（(]+\.py)")

STUB = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>Coverage for {path}</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
         max-width: 46rem; margin: 3rem auto; padding: 0 1.5rem; line-height: 1.75;
         color: #222; }}
  code {{ background: #f4f4f6; padding: .1em .35em; border-radius: 3px; }}
  .note {{ border-left: 3px solid #d0900c; background: #fdf6e6; padding: .9rem 1.2rem;
          margin: 1.4rem 0; }}
  table {{ border-collapse: collapse; margin: 1.2rem 0; }}
  th, td {{ border: 1px solid #ddd; padding: .4rem .8rem; text-align: left; }}
  th {{ background: #f4f4f6; }}
  a {{ color: #1a5fb4; }}
</style>
</head>
<body>
<h1>{path}</h1>

<div class="note">
本交付版本未包含该模块的实现，逐行标注一并省略。覆盖率数据不受影响。
</div>

<h2>覆盖率数据（不受影响）</h2>

<table>
<tr><th>项</th><th>值</th></tr>
<tr><td>语句数</td><td>{n_statements}</td></tr>
<tr><td>未覆盖</td><td>{n_missing}</td></tr>
<tr><td>覆盖率</td><td>{percent}</td></tr>
</table>

<p>本文件的覆盖率数字在汇总页上完整保留，全项目总计 78.79% 亦未改动——
该结果在完整代码上运行 161 项测试得出。</p>

<p>完整实现与完整覆盖率报告保留在私有仓库，可按赛事要求向评审开放访问权限。</p>

<p><a href="index.html">← 返回覆盖率汇总</a></p>
</body>
</html>
"""


def redacted_paths() -> set[str]:
    """裁剪清单里属于覆盖率范围（backend/app/**）的文件，转成报告用的相对路径。"""
    out = set()
    for directory in REDACT_DIRS:
        if not directory.startswith(PREFIX + "app/"):
            continue  # backend/tools 不在覆盖率范围内（source = ["app"]）
        for path in (REPO / directory).rglob("*.py"):
            label = path.relative_to(REPO).as_posix()
            if label in KEEP_DECLARATIVE or path.name == "__init__.py":
                continue
            out.add(label[len(PREFIX):])
    return out


def stats_index() -> dict[str, dict[str, str]]:
    """从 status.json 取每个文件的精确统计。

    页面 HTML 里只有百分比，语句数与未覆盖数的标记在不同 coverage 版本里不稳定；
    status.json 是报告自带的机器可读汇总，直接读它，数字与汇总页必然一致。
    """
    data = json.loads((COVERAGE / "status.json").read_text(encoding="utf-8"))
    out: dict[str, dict[str, str]] = {}
    for entry in (data.get("files") or {}).values():
        index = entry.get("index") or {}
        nums = index.get("nums") or {}
        statements = nums.get("n_statements")
        missing = nums.get("n_missing")
        if statements is None or missing is None:
            continue
        covered = statements - missing
        percent = f"{covered / statements * 100:.0f}%" if statements else "—"
        out[index.get("file", "")] = {
            "n_statements": f"{statements:,}",
            "n_missing": f"{missing:,}",
            "percent": percent,
        }
    return out


def main() -> None:
    if not COVERAGE.is_dir():
        print(f"找不到覆盖率报告目录：{COVERAGE}")
        print("先按 交付材料-单元测试/单元测试报告.md 的命令生成，再跑本脚本。")
        raise SystemExit(1)

    targets = redacted_paths()
    stats = stats_index()
    replaced = []

    for page in sorted(COVERAGE.glob("*.html")):
        if page.name in {"index.html", "function_index.html", "class_index.html"}:
            continue
        text = page.read_text(encoding="utf-8", errors="ignore")
        m = TITLE_RE.search(text)
        if not m:
            continue
        path = m.group(1).strip()
        if path not in targets:
            continue
        numbers = stats.get(path) or {
            "n_statements": "见汇总页", "n_missing": "见汇总页", "percent": "见汇总页",
        }
        page.write_text(
            STUB.format(path=html.escape(path), **numbers), encoding="utf-8"
        )
        replaced.append((path, len(text)))

    if not replaced:
        print("没有需要处理的页面（可能已处理过，或报告是用裁剪版代码生成的）")
        return

    print(f"替换 {len(replaced)} 份逐行页：")
    for path, size in sorted(replaced):
        print(f"  {path:48s} 原 {size:>9,} 字符")


if __name__ == "__main__":
    main()
