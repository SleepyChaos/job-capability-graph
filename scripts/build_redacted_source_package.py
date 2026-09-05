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

# 模块级常量是否保留真值。
#
# True：版本号、阈值、权重表按原样写进桩。代价是 COMPONENT_WEIGHTS、
# EVENT_TYPE_WEIGHTS 这类参数会一并交出去；收益是裁剪包能真正启动——非裁剪代码
# 会 import 这些常量，给假值等于让保留下来的功能静默算错，那比交出参数更糟。
# 判断依据同 models.py：常量是声明，不是方法；权重脱离组合方式没有复用价值。
#
# False：常量仍然定义（否则 ImportError），但标量置零、容器置空。此时裁剪包
# **不能保证正确运行**，只适合纯代码审阅。
KEEP_CONSTANT_VALUES = True

# 这些内置异常基类可以安全恢复：桩不 import 任何东西，但内置名一直可用。
# 不恢复的话，`except ValueError` 接不住 DiscoveryError，保留下来的调用方会漏接。
BUILTIN_BASES = {
    "Exception", "BaseException", "ValueError", "TypeError", "KeyError",
    "RuntimeError", "NotImplementedError", "LookupError", "OSError",
}

# 顶层只取源码相关部分；data/ 与交付目录本身不进源码包。
TOP_LEVEL = ["backend", "frontend", "docker-compose.yml", "README.md"]

# 单文件体积上限（字节）。超限的默认跳过，除非在下面的放行名单里。
MAX_FILE_BYTES = 1_000_000

# 超限但必须带上的运行时数据产物。
#
# 裁剪包的目标是「能部署」而不只是「能读」，这几份是跑起来的前提：少了图谱产物，
# 前端的岗位画像图谱直接空白；少了桥接表，人岗匹配的图谱关联对每个岗位都显示
# 「尚未关联」。它们是数据管线的输出，不含任何源码，放行不影响裁剪目的。
RUNTIME_DATA_ALLOW = {
    "frontend/public/job-ecosystem-graph.json",
    "frontend/public/enterprise-industry-graph.json",
    "backend/data/job_graph_bridge.json",
}

# 运行库快照在包内的落点。由 scripts/dump_runtime_db.sh 产出后拷进来；
# 没有它裁剪包能启动但库是空的，演示价值接近于零。
DB_DUMP_SOURCE = Path(".runtime/delivery-images/job_capability_graph.sql.gz")
DB_DUMP_TARGET = "db/job_capability_graph.sql.gz"

SKIP_SUFFIXES = {".tsbuildinfo", ".log", ".pyc"}

# 计入「保留行数」的文件类型。数据产物（.json 图谱）不算源码。
SOURCE_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".html", ".md",
    ".yml", ".yaml", ".toml", ".ini", ".cfg", ".sh", ".sql", ".conf",
}

NOTICE = "交付裁剪版不含本模块实现，完整实现见私有仓库；裁剪范围见根目录《源码裁剪说明.md》"

# 注入到裁剪包里的模块：桩抛这个异常，main.py 的处理器把它映射成 501。
# 不用裸 NotImplementedError 是为了让评审点到被裁功能时看到有意声明，
# 而不是一个 500 崩溃——后者看起来像工程没做完。
REDACTED_MODULE = '''"""交付裁剪版的功能占位异常。

本文件不属于原始代码，由 scripts/build_redacted_source_package.py 在构建裁剪包时
注入。被裁模块的桩函数抛出 RedactedFeatureError，main.py 中注册的处理器将其映射为
HTTP 501，响应体指向在线部署——评审因此能区分「这个功能被裁了」与「这个功能坏了」。
"""

from __future__ import annotations

ONLINE_DEPLOYMENT = "http://122.51.220.41:8080/"


class RedactedFeatureError(NotImplementedError):
    """调用到了交付裁剪版中未包含实现的模块。"""

    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        super().__init__(detail or "交付裁剪版不含该功能的实现")
'''

# 追加到裁剪包 app/main.py 末尾的处理器。原仓库的 main.py 不动。
MAIN_PATCH = '''

# ─── 以下由 scripts/build_redacted_source_package.py 在构建裁剪包时追加 ───
#
# 被裁模块的桩抛 RedactedFeatureError。没有这个处理器的话 FastAPI 回 500，
# 评审看到的是崩溃；映射成 501 Not Implemented 并带上在线地址，才对得上
# 《源码裁剪说明.md》里「主动声明的裁剪」这个口径。
from fastapi.responses import JSONResponse  # noqa: E402

from app.core.redacted import ONLINE_DEPLOYMENT, RedactedFeatureError  # noqa: E402


@app.exception_handler(RedactedFeatureError)
async def _redacted_feature_handler(_: Request, exc: RedactedFeatureError):
    return JSONResponse(
        status_code=501,
        content={
            "error": "redacted_in_delivery",
            "message": "本功能的实现未包含在交付裁剪版源码包中。",
            "detail": exc.detail or None,
            "online_deployment": ONLINE_DEPLOYMENT,
            "reference": "源码裁剪说明.md",
        },
    )
'''


@dataclass
class Manifest:
    redacted: list[dict] = field(default_factory=list)
    oversize: list[dict] = field(default_factory=list)
    copied_files: int = 0
    copied_lines: int = 0
    db_dump: int | None = None


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


def stub_body(indent: str, qualname: str) -> list[str]:
    return [f'{indent}raise RedactedFeatureError("{qualname}")']


def module_name(label: str) -> str:
    """`backend/app/modules/discovery/service.py` → `app.modules.discovery.service`。"""
    return label[len("backend/"):-len(".py")].replace("/", ".")


def externally_imported() -> dict[str, set[str]]:
    """非裁剪代码从各裁剪模块 import 了哪些名字。

    桩必须保留这些名字，**包括下划线开头的**：`_NearestRole` 虽然按命名是私有的，
    却被跨模块导入，只按「是否公开」过滤会漏掉它，包就 ImportError。
    """
    redacted_mods = {
        module_name(rel(p))
        for directory in REDACT_DIRS
        for p in (REPO / directory).rglob("*.py")
        if rel(p) not in KEEP_DECLARATIVE and p.name != "__init__.py"
    }
    used: dict[str, set[str]] = {}
    for path in tracked_files():
        if path.suffix != ".py" or should_redact(path):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in redacted_mods:
                used.setdefault(node.module, set()).update(a.name for a in node.names)
    return used


def blank_value(node: ast.expr) -> str:
    """KEEP_CONSTANT_VALUES=False 时，按原值的类型给一个同型空值。"""
    if isinstance(node, ast.Dict):
        return "{}"
    if isinstance(node, ast.List):
        return "[]"
    if isinstance(node, (ast.Set, ast.SetComp)):
        return "frozenset()"
    if isinstance(node, ast.Tuple):
        return "()"
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, str):
            return '""'
        if isinstance(value, bool):
            return "False"
        if isinstance(value, (int, float)):
            return "0"
    return "None"


def render_stub(source: str, path_label: str, keep_names: dict[str, set[str]]) -> str:
    """把一份实现文件改写成保留公开签名的桩。

    保留原模块的文档字符串——它说明这个模块做什么，是评审需要的信息，
    且不暴露实现。签名里的类型注解靠 `from __future__ import annotations`
    延迟求值，桩文件因此不需要保留任何 import 也能被导入。
    """
    tree = ast.parse(source)
    doc = ast.get_docstring(tree)
    mod = module_name(path_label)
    wanted = keep_names.get(mod, set())

    def exported(name: str) -> bool:
        """公开的一律保留；私有的只在被外部导入时保留。"""
        return not name.startswith("_") or name in wanted

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
    # 原模块的 import 原样保留。
    #
    # 它们声明的是依赖关系，不是方法本身，泄露风险与保留常量同级；而少了它们，
    # 桩里保留的 dataclass 字段默认值（`field(default_factory=Counter)`）、类型
    # 注解等会在导入期 NameError，整个后端起不来。`__future__` 必须排除——
    # 它只能出现在文件最前，重复一次是 SyntaxError。
    for node in tree.body:
        if isinstance(node, ast.Import):
            lines.append(ast.unparse(node))
        elif isinstance(node, ast.ImportFrom) and node.module != "__future__":
            lines.append(ast.unparse(node))
    lines.append("from dataclasses import dataclass, field  # noqa: F401")
    lines.append("from app.core.redacted import RedactedFeatureError")
    lines.append("")

    kept = 0
    for node in tree.body:
        # ── 模块级常量 ──
        # 必须保留：非裁剪代码 import 它们，缺一个就是 ImportError（整个后端起不来）。
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = (
                [t.id for t in node.targets if isinstance(t, ast.Name)]
                if isinstance(node, ast.Assign)
                else ([node.target.id] if isinstance(node.target, ast.Name) else [])
            )
            value = node.value
            # 私有常量也保留：公开常量常由私有常量算出
            # （`CHANNEL_WEIGHTS = {k: v / _WEIGHT_SUM for ...}`），
            # 按公开性筛只会一路踩 NameError。常量是声明，不是方法。
            for name in targets:
                if value is None:
                    continue
                kept += 1
                rendered = ast.unparse(value) if KEEP_CONSTANT_VALUES else blank_value(value)
                lines.append(f"{name} = {rendered}")
            if targets:
                lines.append("")
            continue

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not exported(node.name):
                continue
            kept += 1
            if node.decorator_list:
                names = ", ".join(ast.unparse(d) for d in node.decorator_list)
                lines.append(f"# 原装饰器：{names}")
            lines.append(signature(node))
            if (inner := ast.get_docstring(node)):
                first = safe_doc(inner.strip().splitlines()[0])
                lines.append(f'    """{first}"""')
            lines.extend(stub_body("    ", f"{mod}.{node.name}"))
            lines.append("")

        elif isinstance(node, ast.ClassDef):
            if not exported(node.name):
                continue
            kept += 1
            # dataclass 的装饰器要保留：非裁剪代码会构造实例、按字段名取值，
            # 只留一个空 class 会在运行期炸在属性访问上。
            is_dc = False
            for deco in node.decorator_list:
                text = ast.unparse(deco)
                if "dataclass" in text:
                    lines.append(f"@{text}")
                    is_dc = True
                else:
                    lines.append(f"# 原装饰器：{text}")
            # 内置异常基类可以恢复（见 BUILTIN_BASES）；其余基类不保留——
            # 桩不 import 任何业务模块，写上去会在导入期求值失败。
            keep_bases, dropped = [], []
            for base in node.bases:
                text = ast.unparse(base)
                (keep_bases if text in BUILTIN_BASES else dropped).append(text)
            if dropped:
                lines.append(f"# 原基类（未保留）：{', '.join(dropped)}")
            suffix = f"({', '.join(keep_bases)})" if keep_bases else ""
            lines.append(f"class {node.name}{suffix}:")
            if (inner := ast.get_docstring(node)):
                first = safe_doc(inner.strip().splitlines()[0])
                lines.append(f'    """{first}"""')

            body_lines: list[str] = []
            if is_dc:
                # 字段声明原样保留：它们是数据形状，不是算法。注解靠
                # `from __future__ import annotations` 延迟求值，不会因为
                # 引用了未 import 的类型而在导入期失败。
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        body_lines.append(f"    {ast.unparse(item)}")
            for method in node.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and not method.name.startswith("_"):
                    body_lines.append(f"    {signature(method)}")
                    body_lines.extend(stub_body("        ", f"{mod}.{node.name}.{method.name}"))
            lines.extend(body_lines or ["    pass"])
            lines.append("")

    if kept == 0:
        lines.append("# 本文件无对外接口（原实现为脚本入口或私有辅助函数）。")
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


def collect(manifest: Manifest, keep_names: dict[str, set[str]]) -> None:
    for item in sorted(tracked_files()):
        if not item.exists() or item.suffix in SKIP_SUFFIXES:
            continue

        target = PACKAGE / item.relative_to(REPO)
        target.parent.mkdir(parents=True, exist_ok=True)

        if should_redact(item):
            text = item.read_text(encoding="utf-8")
            original_lines = len(text.splitlines())
            target.write_text(render_stub(text, rel(item), keep_names), encoding="utf-8")
            manifest.redacted.append({"path": rel(item), "lines": original_lines})
            continue

        size = item.stat().st_size
        if size > MAX_FILE_BYTES and rel(item) not in RUNTIME_DATA_ALLOW:
            manifest.oversize.append({"path": rel(item), "bytes": size})
            continue

        shutil.copy2(item, target)
        manifest.copied_files += 1
        # 只统计源码行数。图谱产物是单份 39.5MB 的 JSON，算进去会让「保留 X 行」
        # 从 6 万变成 89 万——那个数字要出现在交付文档里，不能是数据产物撑出来的。
        if item.suffix in SOURCE_SUFFIXES:
            try:
                manifest.copied_lines += len(item.read_text(encoding="utf-8").splitlines())
            except (UnicodeDecodeError, ValueError):
                pass


# 裁剪包专用编排。仓库那份 docker-compose.yml 不能用：它有 bootstrap 服务，
# 要靠 backend/tools/ 从核心 XLSX 建库，而 tools 在裁剪包里全是桩。
TRIMMED_COMPOSE = '''# 交付裁剪版专用编排。
#
# 与仓库根目录那份的区别，以及为什么必须不同：
#   - 去掉 bootstrap：它调用 backend/tools/ 从核心 XLSX 重建数据，而 tools/ 在
#     裁剪包里全是桩，跑起来必然失败。改为随包分发已审计的库快照。
#   - 去掉 restore/migrate：快照已是 Alembic head 结构，MySQL 官方 entrypoint
#     在数据目录为空时自动导入 db/ 下的 .sql.gz，不需要额外服务。
#   - backend / frontend 仍为 build:，从本包源码构建——这是源码交付物，
#     评审应当能亲自构建。
#
# 被裁模块的计算与写入端点返回 HTTP 501 并指向在线部署，属预期行为，不是故障。
services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: root_password_change_me
      MYSQL_DATABASE: job_capability_graph
      MYSQL_USER: app
      MYSQL_PASSWORD: app_password_change_me
    command: ["--character-set-server=utf8mb4", "--collation-server=utf8mb4_unicode_ci"]
    volumes:
      - mysql-data:/var/lib/mysql
      # 首次启动时由官方 entrypoint 自动导入（约 660MB SQL，需要几分钟）
      - ./db:/docker-entrypoint-initdb.d:ro
    healthcheck:
      # 首启要等导入完成，retries 放宽；否则导入没完就被判不健康
      test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1", "-uroot", "-proot_password_change_me"]
      interval: 10s
      timeout: 5s
      retries: 60
      start_period: 60s

  backend:
    build: ./backend
    environment:
      APP_DATABASE_URL: mysql+pymysql://app:app_password_change_me@mysql:3306/job_capability_graph?charset=utf8mb4
      APP_AUTH_SECRET: ${APP_AUTH_SECRET:-change-me-in-production}
    ports:
      - "8000:8000"
    depends_on:
      mysql:
        condition: service_healthy
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports:
      - "8080:80"
    depends_on:
      - backend
    restart: unless-stopped

volumes:
  mysql-data:
'''


def inject_db_dump(manifest: Manifest) -> None:
    """把运行库快照拷进包。缺失时明确报出来，不静默产出一个跑不出数据的包。"""
    source = REPO / DB_DUMP_SOURCE
    target = PACKAGE / DB_DUMP_TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        manifest.db_dump = None
        return
    shutil.copy2(source, target)
    manifest.db_dump = source.stat().st_size


def inject_runtime() -> None:
    """写入裁剪包专有的运行期支撑：占位异常模块 + main.py 的 501 处理器。

    只改包内副本，仓库里的 app/main.py 一个字不动——裁剪是交付形态的事，
    不该渗进正式代码。
    """
    (PACKAGE / "backend/app/core/redacted.py").write_text(REDACTED_MODULE, encoding="utf-8")
    main_py = PACKAGE / "backend/app/main.py"
    main_py.write_text(main_py.read_text(encoding="utf-8") + MAIN_PATCH, encoding="utf-8")
    # 覆盖掉从仓库拷来的那份 compose：它带 bootstrap，在裁剪包里必然失败。
    (PACKAGE / "docker-compose.yml").write_text(TRIMMED_COMPOSE, encoding="utf-8")


def main() -> None:
    if PACKAGE.exists():
        shutil.rmtree(PACKAGE)
    PACKAGE.mkdir(parents=True)

    keep_names = externally_imported()
    manifest = Manifest()
    collect(manifest, keep_names)
    inject_runtime()
    inject_db_dump(manifest)

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

    if manifest.db_dump:
        print(f"运行库快照 {manifest.db_dump / 1024 / 1024:.0f} MB 已打包")
    else:
        print("⚠ 未找到运行库快照，包内数据库为空——先跑 bash scripts/dump_runtime_db.sh")
    print(f"裁剪 {payload['redacted_files']} 个文件 / {payload['redacted_lines']:,} 行")
    print(f"保留 {payload['copied_files']} 个文件 / {payload['copied_lines']:,} 行")
    print(f"体积超限跳过 {len(manifest.oversize)} 个文件")


if __name__ == "__main__":
    main()
