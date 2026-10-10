"""Environment-only DeepSeek settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class LlmConfigurationError(RuntimeError):
    """The local model configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class DeepSeekSettings:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-flash"
    timeout_seconds: float = 120

    @classmethod
    def from_environ(cls, environ: Mapping[str, str]) -> "DeepSeekSettings":
        api_key = environ.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise LlmConfigurationError("尚未配置 DEEPSEEK_API_KEY")
        base_url = environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/")
        model = environ.get("DEEPSEEK_MODEL", "deepseek-flash").strip()
        if not base_url.startswith(("https://", "http://")) or not model:
            raise LlmConfigurationError("DeepSeek 地址或模型配置无效")
        try:
            timeout = float(environ.get("DEEPSEEK_REQUEST_TIMEOUT_SECONDS", "120"))
        except ValueError as exc:
            raise LlmConfigurationError("DeepSeek 请求超时必须是数字") from exc
        if not 1 <= timeout <= 600:
            raise LlmConfigurationError("DeepSeek 请求超时必须在1～600秒之间")
        return cls(api_key=api_key, base_url=base_url, model=model, timeout_seconds=timeout)
