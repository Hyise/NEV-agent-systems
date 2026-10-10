"""Minimal DeepSeek JSON-mode HTTP client with sanitized failures."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from .config import DeepSeekSettings, LlmConfigurationError
from .domain import RenderedPrompt


class LlmError(RuntimeError):
    """Base class for safe, user-presentable model errors."""


class LlmAuthenticationError(LlmError):
    pass


class LlmTransientError(LlmError):
    pass


class LlmInvalidResponseError(LlmError):
    pass


@dataclass(frozen=True, slots=True)
class JsonCompletion:
    payload: Any
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_tokens: int
    finish_reason: str


class DeepSeekClient:
    def __init__(
        self,
        settings: DeepSeekSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ):
        self.settings = settings
        self._client = httpx.Client(
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
            transport=transport,
            headers={"Authorization": f"Bearer {settings.api_key}"},
        )

    def close(self) -> None:
        self._client.close()

    def complete_json(self, prompt: RenderedPrompt, *, max_tokens: int) -> JsonCompletion:
        request_body = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": prompt.system_prompt},
                {"role": "user", "content": prompt.user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "max_tokens": max_tokens,
            "stream": False,
        }
        try:
            response = self._client.post("/chat/completions", json=request_body)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise LlmTransientError("DeepSeek 网络请求暂时失败") from exc

        if response.status_code in (401, 403):
            raise LlmAuthenticationError("DeepSeek 认证失败，请检查本机 API Key 或账户状态")
        if response.status_code == 429 or response.status_code >= 500:
            raise LlmTransientError("DeepSeek 服务暂时不可用，请稍后重试")
        if response.status_code >= 400:
            raise LlmInvalidResponseError(f"DeepSeek 请求被拒绝（HTTP {response.status_code}）")

        try:
            body = response.json()
            choice = body["choices"][0]
            finish_reason = choice["finish_reason"]
            content = choice["message"]["content"]
            usage = body.get("usage", {})
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LlmInvalidResponseError("DeepSeek 响应结构无效") from exc
        if finish_reason == "length":
            raise LlmInvalidResponseError("DeepSeek 响应因长度限制被截断")
        if not isinstance(content, str) or not content.strip():
            raise LlmInvalidResponseError("DeepSeek 返回了空内容")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LlmInvalidResponseError("DeepSeek 返回的内容不是有效 JSON") from exc

        return JsonCompletion(
            payload=payload,
            input_tokens=_safe_token(usage, "prompt_tokens"),
            output_tokens=_safe_token(usage, "completion_tokens"),
            total_tokens=_safe_token(usage, "total_tokens"),
            cached_tokens=_safe_token(usage, "prompt_cache_hit_tokens"),
            finish_reason=str(finish_reason),
        )


def _safe_token(usage: Any, key: str) -> int:
    value = usage.get(key, 0) if isinstance(usage, dict) else 0
    return value if isinstance(value, int) and value >= 0 else 0


__all__ = [
    "DeepSeekClient",
    "JsonCompletion",
    "LlmAuthenticationError",
    "LlmConfigurationError",
    "LlmInvalidResponseError",
    "LlmTransientError",
]
