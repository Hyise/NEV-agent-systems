"""Versioned prompt rendering without runtime secrets or network access."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from .domain import CriterionSnapshot, PromptManifest, RenderedPrompt


class PromptRenderer:
    def __init__(self, template_dir: Path | None = None):
        self.template_dir = template_dir or Path(__file__).with_name("prompts")

    def _render(self, filename: str, version: str, replacements: dict[str, Any]) -> RenderedPrompt:
        source = (Path(self.template_dir) / filename).read_text(encoding="utf-8")
        body = source
        for token, value in replacements.items():
            rendered = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
            body = body.replace(f"__{token}__", rendered)
        return RenderedPrompt(
            system_prompt="你是新能源汽车市场研究与多准则决策分析助手。只输出有效 JSON。",
            user_prompt=body,
            manifest=PromptManifest(
                version=version,
                sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
            ),
        )

    def discovery_batch(self, reviews: Sequence[str]) -> RenderedPrompt:
        return self._render(
            "criteria_discovery_v1.txt",
            "criteria-discovery-v1",
            {"REVIEWS_JSON": list(reviews)},
        )

    def criteria_merge(self, clues: Sequence[dict[str, Any]]) -> RenderedPrompt:
        return self._render(
            "criteria_merge_v1.txt",
            "criteria-merge-v1",
            {"CLUES_JSON": list(clues)},
        )

    def review_annotation(
        self,
        criteria: Sequence[CriterionSnapshot],
        review_text: str,
    ) -> RenderedPrompt:
        schema = [{"name": item.name, "labels": item.labels} for item in criteria]
        return self._render(
            "review_annotation_v1.txt",
            "review-annotation-v1",
            {"CRITERIA_JSON": schema, "REVIEW_TEXT": review_text},
        )

