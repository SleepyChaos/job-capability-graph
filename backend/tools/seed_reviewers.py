"""幂等种子审核员脚本。

开发期审核与审批接口依赖 app_user 中的 reviewer/admin 身份（X-Reviewer-Code 头）。
本脚本为演示与联调种子两个账号，重复执行不会产生重复记录。

用法：
    uv run python tools/seed_reviewers.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.data_center.models import AppUser

SEED_USERS = [
    {"user_code": "reviewer-demo", "display_name": "数据审核员（演示）", "role_code": "reviewer"},
    {"user_code": "admin-demo", "display_name": "系统管理员（演示）", "role_code": "admin"},
]


def main() -> None:
    with SessionLocal() as db:
        for item in SEED_USERS:
            existing = db.scalar(select(AppUser).where(AppUser.user_code == item["user_code"]))
            if existing is not None:
                existing.is_active = True
                existing.role_code = item["role_code"]
                print(f"已存在，保持激活: {item['user_code']}")
                continue
            db.add(AppUser(**item, is_active=True))
            print(f"已创建: {item['user_code']} ({item['role_code']})")
        db.commit()


if __name__ == "__main__":
    main()
