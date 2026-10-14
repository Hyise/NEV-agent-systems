"""Strict public contracts and domain errors for review asset management."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Tag = Annotated[str, Field(min_length=1, max_length=30)]


def _unique_tags(tags: list[str]) -> list[str]:
    normalized = [tag.strip() for tag in tags]
    if any(not tag for tag in normalized):
        raise ValueError("标签不能为空")
    if len(normalized) != len(set(normalized)):
        raise ValueError("标签不能重复")
    return normalized


class MetadataPatchBody(StrictModel):
    revision: int = Field(ge=1)
    tags: list[Tag] = Field(max_length=20)
    note: str = Field(max_length=1000)
    analysis_enabled: bool

    @field_validator("tags")
    @classmethod
    def unique_tags(cls, tags: list[str]) -> list[str]:
        return _unique_tags(tags)


class BatchMetadataPatchBody(StrictModel):
    asset_ids: list[str] = Field(min_length=1, max_length=500)
    analysis_enabled: bool | None = None
    add_tags: list[Tag] = Field(default_factory=list, max_length=20)
    remove_tags: list[Tag] = Field(default_factory=list, max_length=20)

    @field_validator("asset_ids")
    @classmethod
    def unique_asset_ids(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("资产ID不能为空")
        if len(normalized) != len(set(normalized)):
            raise ValueError("资产ID不能重复")
        return normalized

    @field_validator("add_tags", "remove_tags")
    @classmethod
    def normalize_tags(cls, tags: list[str]) -> list[str]:
        return _unique_tags(tags)

    @model_validator(mode="after")
    def contains_an_operation(self):
        if (
            self.analysis_enabled is None
            and not self.add_tags
            and not self.remove_tags
        ):
            raise ValueError("至少选择一种批量修改操作")
        if set(self.add_tags) & set(self.remove_tags):
            raise ValueError("同一标签不能同时添加和移除")
        return self


class ImportReviewItem(StrictModel):
    series_id: str = Field(pattern=r"^\d+$", max_length=100)
    series_name: str = Field(min_length=1, max_length=200)
    review_id: str | None = Field(default=None, min_length=1, max_length=200)
    source_url: str | None = Field(default=None, max_length=2000)
    original_review: dict[str, Any]

    @field_validator("source_url")
    @classmethod
    def https_source_url(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("https://"):
            raise ValueError("来源网址必须使用https")
        return value


class ImportBatchBody(StrictModel):
    items: list[Any]
    payload_bytes: int = Field(ge=0)


class ImportConfirmBody(ImportBatchBody):
    validation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class AssetNotFound(LookupError):
    pass


class AssetConflict(ValueError):
    pass


class AssetGone(LookupError):
    def __init__(self, audit: dict):
        super().__init__("评论资产已永久删除")
        self.audit = audit


class ImportValidationError(ValueError):
    def __init__(self, result: dict[str, Any]):
        super().__init__("导入数据未通过校验")
        self.result = result
