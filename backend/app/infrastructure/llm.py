"""LLM 能力网关（总体设计 §12、后端设计 §2.1）。

首期实现要点：
- OpenAI 兼容 Chat Completions 接口，默认 DeepSeek；
- 无 API Key 或调用失败时返回 None，由调用方走规则降级，不抛异常中断业务；
- 结构化输出要求 JSON，并做 Schema 校验；
- 幻觉防控：只把锁定的机械事实作为上下文，要求每个结论回指 evidence；
- LLM 不进入机械评分，也不得改写已锁定的机械事实（见 discovery 表达层）。

本模块只做"生成与校验"，不直接写库；落库由调用方在事务中完成。
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

GATEWAY_VERSION = "llm_gateway_v1"


@dataclass(frozen=True)
class LLMResult:
    model: str
    prompt_version: str
    content: str
    parsed_json: dict | None


class LLMUnavailableError(RuntimeError):
    """Raised internally when the gateway cannot reach a provider."""


def llm_available() -> bool:
    settings = get_settings()
    return bool(settings.llm_api_key)


def _post_chat(messages: list[dict], *, json_mode: bool) -> str:
    settings = get_settings()
    payload: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": 0.2,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    request = urllib.request.Request(
        f"{settings.llm_base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.llm_timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise LLMUnavailableError(str(exc)) from exc
    try:
        return body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMUnavailableError(f"unexpected response: {body}") from exc


def generate(
    *,
    system_prompt: str,
    user_prompt: str,
    prompt_version: str,
    json_mode: bool = False,
) -> LLMResult | None:
    """调用 LLM；不可用或失败时返回 None（调用方降级），不抛异常。"""
    if not llm_available():
        logger.info("LLM 网关无 API Key，返回 None 触发规则降级（prompt=%s）", prompt_version)
        return None
    settings = get_settings()
    try:
        content = _post_chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            json_mode=json_mode,
        )
    except LLMUnavailableError as exc:
        logger.warning("LLM 调用失败（prompt=%s）：%s", prompt_version, exc)
        return None
    parsed = None
    if json_mode:
        parsed = _safe_json(content)
        if parsed is None:
            logger.warning("LLM 返回非 JSON，降级（prompt=%s）", prompt_version)
            return None
    return LLMResult(
        model=settings.llm_model,
        prompt_version=prompt_version,
        content=content,
        parsed_json=parsed,
    )


def _safe_json(content: str) -> dict | None:
    try:
        loaded = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def validate_schema(data: dict, required_keys: set[str]) -> bool:
    """最小 Schema 校验：必需键齐全且非空。"""
    if not isinstance(data, dict):
        return False
    return all(data.get(key) for key in required_keys)
