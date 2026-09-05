"""生成「交付裁剪版」源码包。

赛事交付需要提交源代码，但新岗位发现推演、岗位聚类、结构化抽取与离线管线属于
本项目的核心方法，不适合以可直接复用的形态分发。本脚本从完整仓库生成一份裁剪
副本：被裁模块保留目录、文件名、公开接口签名与原模块文档字符串，实现替换为
抛 NotImplementedError 的桩，使评审能看清「这里有什么、被裁了什么」，而不是
看到一个像是没写完的工程。

裁剪是**有意声明**的，不是隐瞒：脚本同时产出清单，由根目录《源码裁剪说明.md》
逐条列出被裁文件与原始行数。完整实现始终保留在私有仓库，可按赛事要求授权评审。

用法：
    python scripts/build_redacted_source_package.py

产物：
    交付材料-源代码/            裁剪后的源码树
    交付材料-源代码/裁剪清单.json  供说明文档引用的机器可读清单
"""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "交付材料-源代码"
PACKAGE = OUT / "src"

# 被裁剪的实现文件。按目录声明，models.py 例外见 KEEP_DECLARATIVE。
REDACT_DIRS = [
    "backend/app/modules/discovery",
    "backend/app/modules/clustering",
    "backend/app/modules/extraction",
    "backend/tools",
]

# 纯 SQLAlchemy 表声明，不含算法；裁掉它们只会让迁移与接口模型失去参照，
# 对保护核心方法没有帮助。保留并在说明文档中写明这一例外。
KEEP_DECLARATIVE = {
    "backend/app/modules/discovery/models.py",
    "backend/app/modules/clustering/models.py",
}

# 顶层只取源码相关部分；data/ 与交付目录本身不进源码包。
TOP_LEVEL = ["backend", "frontend", "docker-compose.yml", "README.md"]

# 单文件体积上限（字节）。图谱产物是数据管线的输出而非源码，超限的整份跳过。
MAX_FILE_BYTES = 1_000_000

SKIP_SUFFIXES = {".tsbuildinfo", ".log", ".pyc"}

NOTICE = "交付裁剪版不含本模块实现，完整实现见私有仓库；裁剪范围见根目录《源码裁剪说明.md》"


@dataclass
class Manifest:
    redacted: list[dict] = field(default_factory=list)
    oversize: list[dict] = field(default_factory=list)
    copied_files: int = 0
    copied_lines: int = 0


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    args = ast.unparse(node.args)
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{prefix} {node.name}({args}){returns}:"


def safe_doc(text: str) -> str:
    """把原文档字符串的内容转成能安全放进三引号里的形式。

    原样回写会踩两个坑：反斜杠被当成转义序列（`\\N` 直接是 SyntaxError），
    以及内容里自带 `\"\"\"` 时提前闭合。两者都先转义掉。
    """
    return text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')


def stub_body(indent: str) -> list[str]:
    return [f'{indent}raise NotImplementedError("{NOTICE}")']


def render_stub(source: str, path_label: str) -> str:
    """把一份实现文件改写成保留公开签名的桩。

    保留原模块的文档字符串——它说明这个模块做什么，是评审需要的信息，
    且不暴露实现。签名里的类型注解靠 `from __future__ import annotations`
    延迟求值，桩文件因此不需要保留任何 import 也能被导入。
    """
    tree = ast.parse(source)
    doc = ast.get_docstring(tree)

    lines: list[str] = ['"""']
    if doc:
        lines.extend(safe_doc(doc.strip()).splitlines())
        lines.append("")
    else:
        lines.append(f"{path_label}（交付裁剪版）。")
        lines.append("")
    lines.append("—— 交付裁剪声明 ——")
    lines.append("本文件的实现已按根目录《源码裁剪说明.md》移除，仅保留公开接口签名，")
    lines.append("以便评审确认接口边界与调用关系。完整实现保留在私有仓库，可按赛事要求授权。")
    lines.append('"""')
    lines.append("")
    lines.append("from __future__ import annotations")
    lines.append("")

    exported = 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            exported += 1
            if node.decorator_list:
                names = ", ".join(ast.unparse(d) for d in node.decorator_list)
                lines.append(f"# 原装饰器：{names}")
            lines.append(signature(node))
            if (inner := ast.get_docstring(node)):
                first = safe_doc(inner.strip().splitlines()[0])
                lines.append(f'    """{first}"""')
            lines.extend(stub_body("    "))
            lines.append("")
        elif isinstance(node, ast.ClassDef):
            if node.name.startswith("_"):
                continue
            exported += 1
            if node.decorator_list:
                names = ", ".join(ast.unparse(d) for d in node.decorator_list)
                lines.append(f"# 原装饰器：{names}")
            if node.bases:
                bases = ", ".join(ast.unparse(b) for b in node.bases)
                lines.append(f"# 原基类：{bases}")
            # 基类不保留：桩文件不 import，写上去会在导入期求值失败。
            lines.append(f"class {node.name}:")
            if (inner := ast.get_docstring(node)):
                first = safe_doc(inner.strip().splitlines()[0])
                lines.append(f'    """{first}"""')
            methods = [
                m for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not m.name.startswith("_")
            ]
            if not methods:
                lines.append("    pass")
            for method in methods:
                lines.append(f"    {signature(method)}")
                lines.extend(stub_body("        "))
            lines.append("")

    if exported == 0:
        lines.append("# 本文件无公开接口（原实现为脚本入口或私有辅助函数）。")
        lines.append("")

    return "\n".join(lines)


def should_redact(path: Path) -> bool:
    label = rel(path)
    if label in KEEP_DECLARATIVE:
        return False
    if path.suffix != ".py" or path.name == "__init__.py":
        return False
    return any(label.startswith(d + "/") for d in REDACT_DIRS)


def tracked_files() -> list[Path]:
    """源码包的范围以 git 追踪的文件为准。

    先前按目录名黑名单排除，漏掉了 `backend/.uv-cache/`、`backend/.local/` 这类
    本就被 .gitignore 挡住的环境产物，43MB 的包里绝大部分是它们。改用 git 的
    视角：进版本库的才算源码，缓存、虚拟环境、构建产物一律不进——顺带保证了
    `.env` 这类敏感文件不可能被带出去。
    """
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", *TOP_LEVEL],
        cwd=REPO, capture_output=True, check=True, text=True,
    ).stdout
    return [REPO / name for name in out.split("\0") if name]


def collect(manifest: Manifest) -> None:
    for item in sorted(tracked_files()):
        if not item.exists() or item.suffix in SKIP_SUFFIXES:
            continue

        target = PACKAGE / item.relative_to(REPO)
        target.parent.mkdir(parents=True, exist_ok=True)

        if should_redact(item):
            text = item.read_text(encoding="utf-8")
            original_lines = len(text.splitlines())
            target.write_text(render_stub(text, rel(item)), encoding="utf-8")
            manifest.redacted.append({"path": rel(item), "lines": original_lines})
            continue

        size = item.stat().st_size
        if size > MAX_FILE_BYTES:
            manifest.oversize.append({"path": rel(item), "bytes": size})
            continue

        shutil.copy2(item, target)
        manifest.copied_files += 1
        try:
            manifest.copied_lines += len(item.read_text(encoding="utf-8").splitlines())
        except (UnicodeDecodeError, ValueError):
            pass


def main() -> None:
    if PACKAGE.exists():
        shutil.rmtree(PACKAGE)
    PACKAGE.mkdir(parents=True)

    manifest = Manifest()
    collect(manifest)

    manifest.redacted.sort(key=lambda item: -item["lines"])
    manifest.oversize.sort(key=lambda item: -item["bytes"])
    payload = {
        "redacted_files": len(manifest.redacted),
        "redacted_lines": sum(item["lines"] for item in manifest.redacted),
        "redacted": manifest.redacted,
        "oversize_excluded": manifest.oversize,
        "copied_files": manifest.copied_files,
        "copied_lines": manifest.copied_lines,
    }
    (OUT / "裁剪清单.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"裁剪 {payload['redacted_files']} 个文件 / {payload['redacted_lines']:,} 行")
    print(f"保留 {payload['copied_files']} 个文件 / {payload['copied_lines']:,} 行")
    print(f"体积超限跳过 {len(manifest.oversize)} 个文件")


if __name__ == "__main__":
    main()
