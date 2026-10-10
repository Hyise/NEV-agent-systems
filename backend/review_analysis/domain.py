"""Pure, strict contracts for review analysis."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CriterionSnapshot(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    name: str = Field(min_length=1, max_length=50)
    labels: list[str] = Field(min_length=2, max_length=8)

    @field_validator("labels")
    @classmethod
    def unique_labels(cls, labels: list[str]) -> list[str]:
        if any(not label or len(label) > 80 for label in labels):
            raise ValueError("等级名称需为1～80个字符")
        if len(labels) != len(set(labels)):
            raise ValueError("同一准则的等级不能重复")
        return labels


class ProposalCriterion(StrictModel):
    name: str = Field(min_length=1, max_length=50)
    labels: list[str] = Field(min_length=2, max_length=8)
    similar_terms: list[str] = Field(default_factory=list, max_length=30)
    basis: str = Field(min_length=1, max_length=500)
    evidence: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("labels", "similar_terms", "evidence")
    @classmethod
    def unique_nonempty_values(cls, values: list[str]) -> list[str]:
        if any(not value for value in values):
            raise ValueError("列表内容不能为空")
        if len(values) != len(set(values)):
            raise ValueError("列表内容不能重复")
        return values


class CriteriaProposal(StrictModel):
    criteria: list[ProposalCriterion] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_names(self):
        names = [criterion.name for criterion in self.criteria]
        if len(names) != len(set(names)):
            raise ValueError("准则名称不能重复")
        return self


class ReviewAnnotationItem(StrictModel):
    criterion: str = Field(min_length=1, max_length=50)
    label: str = Field(min_length=1, max_length=80)
    evidence: list[str] = Field(min_length=1, max_length=20)
    basis: str = Field(min_length=1, max_length=500)

    @field_validator("evidence")
    @classmethod
    def unique_evidence(cls, values: list[str]) -> list[str]:
        if any(not value for value in values):
            raise ValueError("证据不能为空")
        if len(values) != len(set(values)):
            raise ValueError("证据不能重复")
        return values


class ReviewAnnotationResult(StrictModel):
    annotations: list[ReviewAnnotationItem] = Field(default_factory=list, max_length=20)
    unmatched_evidence: list[str] = Field(default_factory=list, max_length=30)


class PromptManifest(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    version: str = Field(min_length=1, max_length=100)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RenderedPrompt(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    system_prompt: str = Field(min_length=1)
    user_prompt: str = Field(min_length=1)
    manifest: PromptManifest


class ReviewAsset(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    review_id: str = Field(min_length=1, max_length=200)
    series_id: str = Field(min_length=1, max_length=100)
    series_name: str = Field(min_length=1, max_length=200)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    original_review: dict[str, Any]


class ReviewSnapshot(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    review_id: str = Field(min_length=1, max_length=200)
    series_id: str = Field(min_length=1, max_length=100)
    series_name: str = Field(min_length=1, max_length=200)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis_text: str = Field(min_length=1)
    ordinal: int = Field(ge=0)


class CreateJobCommand(StrictModel):
    project_id: str = Field(min_length=1, max_length=100)
    schema_id: str | None = Field(default=None, max_length=100)
    schema_revision: int | None = Field(default=None, ge=1)
    job_type: Literal["criteria_discovery", "review_annotation"]
    selected_series_ids: list[str] = Field(min_length=1, max_length=1000)
    limit: int | None = Field(default=None, ge=1, le=5000)
    model: str = Field(min_length=1, max_length=200)
    prompt_manifests: list[PromptManifest] = Field(min_length=1, max_length=2)
    schema_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    criteria: list[CriterionSnapshot] = Field(default_factory=list, max_length=20)

    @field_validator("selected_series_ids")
    @classmethod
    def unique_series_ids(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("车系不能重复")
        return values


class ControlAction(StrEnum):
    PAUSE = "pause"
    CANCEL = "cancel"


def schema_fingerprint(criteria: Sequence[CriterionSnapshot]) -> str:
    body = [{"name": item.name, "labels": item.labels} for item in criteria]
    canonical = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def stable_stratified_sample(rows: Sequence[ReviewAsset], limit: int) -> list[ReviewAsset]:
    if limit < 1:
        raise ValueError("样本上限必须大于0")
    groups: dict[str, list[ReviewAsset]] = {}
    for row in rows:
        groups.setdefault(row.series_id, []).append(row)
    for values in groups.values():
        values.sort(
            key=lambda row: hashlib.sha256(
                f"{row.series_id}{row.review_id}{row.content_hash}".encode("utf-8")
            ).hexdigest()
        )
    result: list[ReviewAsset] = []
    series_ids = sorted(groups)
    index = 0
    while len(result) < min(limit, len(rows)):
        added = False
        for series_id in series_ids:
            if index < len(groups[series_id]) and len(result) < limit:
                result.append(groups[series_id][index])
                added = True
        if not added:
            break
        index += 1
    return result


def parse_criteria_proposal(payload: Any) -> CriteriaProposal:
    return CriteriaProposal.model_validate(payload)


def parse_review_annotation(
    payload: Any,
    *,
    criteria: Sequence[CriterionSnapshot],
    review_text: str,
) -> ReviewAnnotationResult:
    result = ReviewAnnotationResult.model_validate(payload)
    allowed = {criterion.name: set(criterion.labels) for criterion in criteria}
    names = [item.criterion for item in result.annotations]
    if len(names) != len(set(names)):
        raise ValueError("同一评论中的准则不能重复")
    for item in result.annotations:
        if item.criterion not in allowed:
            raise ValueError(f"体系外准则：{item.criterion}")
        if item.label not in allowed[item.criterion]:
            raise ValueError(f"体系外等级：{item.criterion}/{item.label}")
        if any(evidence not in review_text for evidence in item.evidence):
            raise ValueError("标注证据必须是评论原文子串")
    if any(evidence not in review_text for evidence in result.unmatched_evidence):
        raise ValueError("未匹配证据必须是评论原文子串")
    if len(result.unmatched_evidence) != len(set(result.unmatched_evidence)):
        raise ValueError("未匹配证据不能重复")
    return result

