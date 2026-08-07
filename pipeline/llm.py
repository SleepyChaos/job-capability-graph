"""LLM 客户端：OpenAI 兼容接口（替换项目二的 coze-coding-dev-sdk）。

未配置 OPENAI_API_KEY 时返回 None，调用方降级为规则方案（聚类画像用启发式命名）。
仅使用标准库 urllib，无额外依赖。
"""
from __future__ import annotations

import json
import re
import urllib.request
from typing import Any

from . import config


def is_available() -> bool:
    return bool(config.LLM_API_KEY)


def chat(messages: list[dict], temperature: float = 0.2, timeout: int = 60) -> str | None:
    """调用 chat/completions，失败或未配置时返回 None。"""
    if not is_available():
        return None
    url = config.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    payload = json.dumps(
        {"model": config.LLM_MODEL, "messages": messages, "temperature": temperature}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.LLM_API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001 - LLM 失败必须可降级
        print(f"[WARN] LLM call failed: {e}")
        return None


def chat_json(system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
    """调用 LLM 并解析 JSON 输出；失败返回 None。"""
    text = chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )
    if text is None:
        return None
    try:
        return extract_json(text)
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] LLM JSON parse failed: {e}")
        return None


def extract_json(text: str) -> dict[str, Any]:
    """与项目二 extract_json 一致：剥代码块围栏后解析 JSON。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise
