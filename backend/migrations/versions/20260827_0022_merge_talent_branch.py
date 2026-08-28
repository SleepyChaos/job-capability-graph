"""汇合 P4 人岗匹配分支的迁移链。

`20260819_0014` → `20260822_0015` 由 P4 分支引入（岗位要求表达式、匹配结果指向
具体岗位），同样自 `20260812_0013` 分出，与主线及图谱分支互不相干。
本修订只做汇合，不含任何 DDL。
"""

from __future__ import annotations

revision: str = "20260827_0022"
down_revision: tuple[str, str] = ("20260827_0021", "20260822_0015")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """两条链各自的变更已在其修订中完成。"""


def downgrade() -> None:
    """回退到分叉状态即可。"""
