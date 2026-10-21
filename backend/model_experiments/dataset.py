from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class DatasetSnapshot:
    records: tuple[dict[str, Any], ...]
    criteria: tuple[str, ...]
    levels: tuple[int, ...]
    source: dict[str, Any]
    sha256: str

    @property
    def months(self) -> tuple[str, ...]:
        return tuple(sorted({str(row["month"]) for row in self.records}))


@dataclass(frozen=True)
class ChronologicalSplit:
    train_months: tuple[str, ...]
    validation_months: tuple[str, ...]
    test_months: tuple[str, ...]

    def indices(self, records: Iterable[dict[str, Any]], partition: str) -> np.ndarray:
        months = set(getattr(self, f"{partition}_months"))
        return np.asarray(
            [index for index, row in enumerate(records) if row["month"] in months],
            dtype=int,
        )


def build_snapshot(records, criteria, source) -> DatasetSnapshot:
    criterion_names = tuple(str(item["name"]) for item in criteria)
    levels = tuple(len(item["labels"]) for item in criteria)
    canonical_records = tuple(
        json.loads(json.dumps(row, ensure_ascii=False)) for row in records
    )
    payload = {
        "criteria": list(criteria),
        "records": canonical_records,
        "source": source,
    }
    digest = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return DatasetSnapshot(
        canonical_records, criterion_names, levels, dict(source), digest
    )


def chronological_split(
    snapshot: DatasetSnapshot, validation_months: int, test_months: int
) -> ChronologicalSplit:
    if validation_months < 1 or test_months < 1:
        raise ValueError("验证集和测试集都至少需要 1 个月")
    months = snapshot.months
    minimum = validation_months + test_months + 1
    if len(months) < minimum:
        raise ValueError(f"至少需要 {minimum} 个连续月份，当前只有 {len(months)} 个")
    test_start = len(months) - test_months
    validation_start = test_start - validation_months
    return ChronologicalSplit(
        months[:validation_start],
        months[validation_start:test_start],
        months[test_start:],
    )
