"""Pure contracts and state rules for comment collection."""

import hashlib
import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class JobMode(StrEnum):
    VERIFICATION = "verification"
    PRODUCTION = "production"


class JobStatus(StrEnum):
    QUEUED = "queued"
    DISCOVERING = "discovering"
    COLLECTING = "collecting"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"
    PARTIAL_FAILED = "partial_failed"


class TaskControlError(ValueError):
    """Raised when a task action is invalid for its current state."""


JobAction = Literal[
    "start",
    "discovery_complete",
    "pause",
    "resume",
    "resume_discovery",
    "stop",
    "complete",
    "partial_fail",
]


_TRANSITIONS: dict[tuple[JobStatus, JobAction], JobStatus] = {
    (JobStatus.QUEUED, "start"): JobStatus.DISCOVERING,
    (JobStatus.DISCOVERING, "discovery_complete"): JobStatus.COLLECTING,
    (JobStatus.DISCOVERING, "pause"): JobStatus.PAUSED,
    (JobStatus.COLLECTING, "pause"): JobStatus.PAUSED,
    (JobStatus.PAUSED, "resume"): JobStatus.COLLECTING,
    (JobStatus.PAUSED, "resume_discovery"): JobStatus.DISCOVERING,
    (JobStatus.QUEUED, "stop"): JobStatus.STOPPED,
    (JobStatus.DISCOVERING, "stop"): JobStatus.STOPPED,
    (JobStatus.COLLECTING, "stop"): JobStatus.STOPPED,
    (JobStatus.PAUSED, "stop"): JobStatus.STOPPED,
    (JobStatus.COLLECTING, "complete"): JobStatus.COMPLETED,
    (JobStatus.COLLECTING, "partial_fail"): JobStatus.PARTIAL_FAILED,
}


def transition_status(current: JobStatus, action: JobAction) -> JobStatus:
    try:
        return _TRANSITIONS[(current, action)]
    except KeyError as exc:
        raise TaskControlError(f"任务状态 {current.value} 不允许执行 {action}") from exc


class CreateJobBody(StrictModel):
    mode: JobMode
    selected_series_ids: list[str] = Field(min_length=1, max_length=1000)
    request_delay_min_seconds: float = Field(default=2, ge=2)
    request_delay_max_seconds: float = Field(default=4, ge=2)
    series_delay_min_seconds: float = Field(default=5, ge=5)
    series_delay_max_seconds: float = Field(default=10, ge=5)

    @field_validator("selected_series_ids")
    @classmethod
    def validate_selected_series_ids(cls, values: list[str]) -> list[str]:
        if any(not value.isdigit() for value in values):
            raise ValueError("车系 ID 必须是数字")
        if len(values) != len(set(values)):
            raise ValueError("车系 ID 不能重复")
        return values

    @model_validator(mode="after")
    def validate_scope_and_delays(self):
        if self.mode is JobMode.VERIFICATION and len(self.selected_series_ids) > 3:
            raise ValueError("功能验证最多选择3个车系")
        if self.request_delay_min_seconds > self.request_delay_max_seconds:
            raise ValueError("分页请求最小间隔不能大于最大间隔")
        if self.series_delay_min_seconds > self.series_delay_max_seconds:
            raise ValueError("车系最小间隔不能大于最大间隔")
        return self

    def to_config(self) -> "JobConfig":
        return JobConfig(
            mode=self.mode,
            max_series=len(self.selected_series_ids),
            max_pages_per_series=2 if self.mode is JobMode.VERIFICATION else None,
            request_delay_min_seconds=self.request_delay_min_seconds,
            request_delay_max_seconds=self.request_delay_max_seconds,
            series_delay_min_seconds=self.series_delay_min_seconds,
            series_delay_max_seconds=self.series_delay_max_seconds,
        )


class JobConfig(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: JobMode
    max_series: int = Field(ge=1, le=1000)
    max_pages_per_series: int | None = Field(default=None, ge=1)
    request_delay_min_seconds: float = Field(ge=2)
    request_delay_max_seconds: float = Field(ge=2)
    series_delay_min_seconds: float = Field(ge=5)
    series_delay_max_seconds: float = Field(ge=5)


class VehicleSeries(StrictModel):
    platform: Literal["autohome"] = "autohome"
    series_id: str = Field(pattern=r"^\d+$")
    series_name: str = Field(min_length=1, max_length=200)
    series_url: str = Field(pattern=r"^https://")
    review_url: str = Field(pattern=r"^https://")
    discovery_rank: int = Field(ge=1)


def canonical_review_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CollectedReview(StrictModel):
    platform: Literal["autohome"] = "autohome"
    review_id: str = Field(min_length=1, max_length=200)
    series_id: str = Field(pattern=r"^\d+$")
    series_name: str = Field(min_length=1, max_length=200)
    source_url: str = Field(pattern=r"^https://")
    original_review: dict[str, Any]
    content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def set_content_hash(self):
        expected = canonical_review_hash(self.original_review)
        if self.content_hash is None:
            self.content_hash = expected
        elif self.content_hash != expected:
            raise ValueError("评论内容哈希与原始对象不一致")
        return self


class ReviewPage(StrictModel):
    series: VehicleSeries
    page_index: int = Field(ge=1)
    page_size: int | None = Field(default=None, ge=1)
    page_count: int | None = Field(default=None, ge=0)
    total: int | None = Field(default=None, ge=0)
    reviews: list[CollectedReview]
