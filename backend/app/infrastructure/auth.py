"""最小 JWT（HS256）认证（计划 D5，需确认清单 Q7/Q8）。

P1 范围：
- 仅用标准库实现 HS256 JWT，无第三方依赖；
- 登录以 app_user.user_code 为凭据（开发期简化，Q7 待确认是否对接外部账号）；
- 过渡期审核与写操作同时接受 Bearer JWT 与既有 X-Reviewer-Code（Q8）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from app.core.config import get_settings

TOKEN_TTL_SECONDS = 8 * 3600
DEFAULT_DEV_SECRET = "dev-only-secret-change-in-production"


class AuthError(ValueError):
    """A user-correctable authentication error."""


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _secret() -> str:
    settings = get_settings()
    return getattr(settings, "auth_secret", "") or DEFAULT_DEV_SECRET


def create_token(*, user_code: str, role_code: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": user_code,
        "role": role_code,
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
    }
    signing_input = (
        f"{_b64url_encode(json.dumps(header).encode())}."
        f"{_b64url_encode(json.dumps(payload).encode())}"
    )
    signature = hmac.new(
        _secret().encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    return f"{signing_input}.{_b64url_encode(signature)}"


def decode_token(token: str) -> dict:
    try:
        signing_input, signature_part = token.rsplit(".", 1)
    except ValueError as exc:
        raise AuthError("令牌格式无效") from exc
    expected = hmac.new(
        _secret().encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(expected, _b64url_decode(signature_part)):
        raise AuthError("令牌签名无效")
    try:
        payload = json.loads(_b64url_decode(signing_input.split(".")[1]))
    except (ValueError, IndexError) as exc:
        raise AuthError("令牌内容无效") from exc
    if int(payload.get("exp", 0)) < int(time.time()):
        raise AuthError("令牌已过期")
    return payload
