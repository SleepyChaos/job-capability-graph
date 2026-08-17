"""窗口 A-1 审计脚本的共享工具:MySQL batch TSV 的反转义与读取。

``mysql --batch`` 输出以制表符分隔;本项目容器内的客户端把 NULL 打印为字面量
``NULL``,并对特殊字符做反斜杠转义:制表符 -> ``\\t``、换行 -> ``\\n``、
反斜杠 -> ``\\\\``。本模块提供还原读取,供各审计分析脚本复用
(纯标准库,不依赖 app 代码)。
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator

_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\"}


def unescape_mysql_field(field: str) -> str | None:
    """还原 mysql --batch 的转义;NULL 值(字面量 ``NULL`` 或 ``\\N``)还原为 None。"""
    if field == "NULL" or field == "\\N":
        return None
    out: list[str] = []
    i = 0
    while i < len(field):
        ch = field[i]
        if ch == "\\" and i + 1 < len(field) and field[i + 1] in _ESCAPES:
            out.append(_ESCAPES[field[i + 1]])
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def iter_mysql_tsv(text: str, columns: list[str]) -> Iterator[dict[str, str | None]]:
    """逐行读取 mysql --batch 输出(跳过表头),返回 {列名: 还原后值} 的字典。"""
    reader = csv.reader(io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE)
    header = next(reader, None)
    if header is None:
        return
    for row in reader:
        if not row:
            continue
        padded = row + [None] * (len(columns) - len(row))
        yield {
            col: (unescape_mysql_field(val) if val is not None else None)
            for col, val in zip(columns, padded, strict=False)
        }
