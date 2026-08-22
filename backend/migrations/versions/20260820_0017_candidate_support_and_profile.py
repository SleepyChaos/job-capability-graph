"""denormalise candidate support count and mark core vs profile technologies

两处改动服务于两个不同的实测结论：

1. `support_job_count`：留出实验显示，同一批候选换成按支撑 JD 数排序，
   Recall@10 从 81.2% 升到 oracle 上界 95.8%。支撑量此前只存在机械事实卡的
   JSON 里，无法排序也无法建索引，这里下沉为列。
   注意这不是要替换评分排序——评分服务的是「哪个候选更可能是新兴岗位」，
   支撑量服务的是「哪个候选对应一个真实存在的岗位」，两个目标不同，
   因此做成可选排序而非替换。

2. `membership_code`：候选的核心组合只有 2–5 个技术，撑不起一份标准化 JD。
   扩展出「画像」层（支撑 JD 中过半出现的技术）供生成与展示使用；
   核心层仍单独保留，候选身份、去重键与覆盖率测量一律只看核心层，
   避免改动分类阈值的标定。

Revision ID: 20260820_0017
Revises: 20260818_0016
Create Date: 2026-08-20 16:40:00.000000
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260820_0017"
down_revision: str | None = "20260818_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "biz_emerging_role_candidate",
        sa.Column("support_job_count", sa.Integer(), nullable=False, server_default="0"),
    )
    # 存量行的支撑量已在机械事实卡里，直接回填，避免重跑推演才能排序。
    # 在 Python 侧解析 JSON 而不用 JSON_EXTRACT：迁移测试跑在 SQLite 上，
    # 各方言的 JSON 函数不通用。
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT emerging_role_candidate_id, mechanical_card_json"
            " FROM biz_emerging_role_candidate"
        )
    ).fetchall()
    for candidate_id, card in rows:
        payload = json.loads(card) if isinstance(card, str) else (card or {})
        try:
            support = int(payload.get("job_count") or 0)
        except (TypeError, ValueError):
            support = 0
        if support:
            bind.execute(
                sa.text(
                    "UPDATE biz_emerging_role_candidate SET support_job_count = :support"
                    " WHERE emerging_role_candidate_id = :candidate_id"
                ),
                {"support": support, "candidate_id": candidate_id},
            )
    op.create_index(
        "idx_emerging_candidate_support",
        "biz_emerging_role_candidate",
        ["support_job_count"],
    )

    op.add_column(
        "rel_candidate_technology",
        sa.Column(
            "membership_code", sa.String(length=16), nullable=False, server_default="core"
        ),
    )
    # 存量关联全部来自核心组合，server_default 已覆盖，无需额外回填。


def downgrade() -> None:
    op.drop_column("rel_candidate_technology", "membership_code")
    op.drop_index("idx_emerging_candidate_support", table_name="biz_emerging_role_candidate")
    op.drop_column("biz_emerging_role_candidate", "support_job_count")
