"""Domain contracts for monthly vehicle-series retail sales."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

SalesPlatform = Literal["autohome", "dongchedi", "yiche"]
MONTH_PATTERN = re.compile(r"^(?P<year>20\d{2})-(?P<month>0[1-9]|1[0-2])$")


class SalesJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"


class SalesStepStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SalesSourceError(RuntimeError):
    """Base error for a platform sales source."""

    code = "source_error"


class SalesAccessVerificationRequired(SalesSourceError):
    """The source requires an interactive verification or authorised API."""

    code = "access_verification_required"


class SalesStructureError(SalesSourceError):
    """The source response no longer matches the verified contract."""

    code = "source_structure_changed"


def validate_month(value: str) -> str:
    if not MONTH_PATTERN.fullmatch(value):
        raise ValueError("月份必须使用 YYYY-MM 格式")
    return value


def month_range(start_month: str, end_month: str) -> list[str]:
    validate_month(start_month)
    validate_month(end_month)
    start_year, start_value = map(int, start_month.split("-"))
    end_year, end_value = map(int, end_month.split("-"))
    start_index = start_year * 12 + start_value - 1
    end_index = end_year * 12 + end_value - 1
    if start_index > end_index:
        raise ValueError("结束月份不能早于开始月份")
    if end_index - start_index >= 24:
        raise ValueError("单个任务最多采集 24 个月")
    return [
        f"{index // 12:04d}-{index % 12 + 1:02d}"
        for index in range(start_index, end_index + 1)
    ]


class CreateSalesJobBody(BaseModel):
    start_month: str
    end_month: str
    platforms: list[SalesPlatform] = Field(min_length=1, max_length=3)

    @field_validator("start_month", "end_month")
    @classmethod
    def valid_month(cls, value: str) -> str:
        return validate_month(value)

    @field_validator("platforms")
    @classmethod
    def unique_platforms(cls, value: list[SalesPlatform]) -> list[SalesPlatform]:
        if len(value) != len(set(value)):
            raise ValueError("来源平台不能重复")
        return value

    @model_validator(mode="after")
    def ordered_months(self):
        month_range(self.start_month, self.end_month)
        return self

    def months(self) -> list[str]:
        return month_range(self.start_month, self.end_month)


class SalesRecord(BaseModel):
    platform: SalesPlatform
    month: str
    series_id: str = Field(min_length=1, max_length=100)
    series_name: str = Field(min_length=1, max_length=200)
    sales_volume: int = Field(ge=0)
    rank: int = Field(ge=1)
    metric: Literal["national_monthly_retail"] = "national_monthly_retail"
    source_url: str = Field(min_length=1, max_length=2000)

    @field_validator("month")
    @classmethod
    def valid_record_month(cls, value: str) -> str:
        return validate_month(value)

    @field_validator("series_id", "series_name", "source_url")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("字段不能为空")
        return stripped


@dataclass(frozen=True)
class SalesMonthResult:
    records: list[SalesRecord]
    snapshot_hash: str
