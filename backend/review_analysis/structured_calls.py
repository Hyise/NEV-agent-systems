"""Retry boundary for model JSON plus business validation."""

import time
from typing import Callable, TypeVar

from .deepseek import JsonCompletion, LlmInvalidResponseError, LlmTransientError
from .domain import RenderedPrompt

T = TypeVar("T")


class StructuredCallExecutor:
    def __init__(self, client, *, sleep: Callable[[float], None] = time.sleep):
        self.client = client
        self.sleep = sleep

    def call(self, prompt: RenderedPrompt, validator: Callable[[object], T], *, max_tokens: int, attempts: int) -> tuple[T, JsonCompletion]:
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                completion = self.client.complete_json(prompt, max_tokens=max_tokens)
                return validator(completion.payload), completion
            except LlmTransientError as exc:
                last_error = exc
            except (ValueError, TypeError) as exc:
                last_error = LlmInvalidResponseError("模型 JSON 不符合业务契约")
                last_error.__cause__ = exc
            if attempt + 1 < attempts:
                self.sleep(min(2**attempt, 4))
        if isinstance(last_error, LlmInvalidResponseError):
            raise last_error
        assert last_error is not None
        raise last_error

