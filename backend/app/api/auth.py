from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.infrastructure.auth import AuthError, create_token, decode_token
from app.modules.data_center.models import AppUser

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    user_code: str = Field(min_length=1, max_length=64)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_code: str
    display_name: str
    role_code: str


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Annotated[Session, Depends(get_db)]):
    """开发期简化登录：仅凭 user_code（Q7 待确认是否对接外部账号体系）。"""
    user = db.scalar(
        select(AppUser).where(
            AppUser.user_code == payload.user_code, AppUser.is_active.is_(True)
        )
    )
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在或已停用")
    token = create_token(user_code=user.user_code, role_code=user.role_code)
    return TokenResponse(
        access_token=token,
        user_code=user.user_code,
        display_name=user.display_name,
        role_code=user.role_code,
    )


def resolve_bearer_user(
    db: Session, authorization: str | None
) -> AppUser | None:
    """从 Authorization: Bearer <jwt> 解析用户；无效或缺返回 None。"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        payload = decode_token(authorization.removeprefix("Bearer ").strip())
    except AuthError:
        return None
    return db.scalar(
        select(AppUser).where(
            AppUser.user_code == payload.get("sub"), AppUser.is_active.is_(True)
        )
    )


@router.get("/me", response_model=TokenResponse)
def me(
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
):
    user = resolve_bearer_user(db, authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="未登录或令牌无效")
    return TokenResponse(
        access_token="",
        user_code=user.user_code,
        display_name=user.display_name,
        role_code=user.role_code,
    )
