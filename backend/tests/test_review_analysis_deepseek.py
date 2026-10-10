import json

import httpx
import pytest

from backend.review_analysis.config import DeepSeekSettings, LlmConfigurationError
from backend.review_analysis.deepseek import (
    DeepSeekClient,
    LlmAuthenticationError,
    LlmInvalidResponseError,
    LlmTransientError,
)
from backend.review_analysis.domain import PromptManifest, RenderedPrompt


SECRET = "sk-test-never-disclose"


def settings() -> DeepSeekSettings:
    return DeepSeekSettings.from_environ({"DEEPSEEK_API_KEY": SECRET})


def prompt() -> RenderedPrompt:
    return RenderedPrompt(
        system_prompt="system",
        user_prompt="user",
        manifest=PromptManifest(version="test-v1", sha256="a" * 64),
    )


def response_payload(content='{"ok": true}', finish_reason="stop"):
    return {
        "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 4,
            "total_tokens": 16,
            "prompt_cache_hit_tokens": 3,
        },
    }


def client_for(handler) -> DeepSeekClient:
    transport = httpx.MockTransport(handler)
    return DeepSeekClient(settings(), transport=transport)


def test_settings_require_key_and_use_safe_defaults():
    with pytest.raises(LlmConfigurationError) as error:
        DeepSeekSettings.from_environ({})
    assert SECRET not in str(error.value)

    configured = settings()
    assert configured.base_url == "https://api.deepseek.com"
    assert configured.model == "deepseek-flash"
    assert configured.timeout_seconds == 120


def test_client_sends_json_mode_and_decodes_usage():
    captured = {}

    def handler(request: httpx.Request):
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=response_payload())

    result = client_for(handler).complete_json(prompt(), max_tokens=600)

    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["authorization"] == f"Bearer {SECRET}"
    assert captured["body"]["model"] == "deepseek-flash"
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert captured["body"]["thinking"] == {"type": "disabled"}
    assert captured["body"]["max_tokens"] == 600
    assert result.payload == {"ok": True}
    assert (result.input_tokens, result.output_tokens, result.total_tokens, result.cached_tokens) == (
        12,
        4,
        16,
        3,
    )


@pytest.mark.parametrize(
    ("status", "error_type"),
    [(401, LlmAuthenticationError), (403, LlmAuthenticationError), (429, LlmTransientError), (500, LlmTransientError)],
)
def test_http_errors_are_classified_without_leaking_key(status, error_type):
    def handler(request: httpx.Request):
        return httpx.Response(status, json={"error": {"message": f"bad {SECRET}"}})

    with pytest.raises(error_type) as error:
        client_for(handler).complete_json(prompt(), max_tokens=20)
    assert SECRET not in str(error.value)


@pytest.mark.parametrize(
    "payload",
    [response_payload(content=""), response_payload(content="not-json"), response_payload(finish_reason="length")],
)
def test_invalid_model_responses_are_rejected_without_response_echo(payload):
    def handler(request: httpx.Request):
        return httpx.Response(200, json=payload)

    with pytest.raises(LlmInvalidResponseError) as error:
        client_for(handler).complete_json(prompt(), max_tokens=20)
    assert SECRET not in str(error.value)
    assert "not-json" not in str(error.value)

