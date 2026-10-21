from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from .dataset import DatasetSnapshot, chronological_split
from .metrics import compute_metrics, normalize_monthly_shares
from .models import MODEL_TYPES


@dataclass(frozen=True)
class Prediction:
    month: str
    model: str
    actual: float
    predicted: float


@dataclass(frozen=True)
class ModelResult:
    key: str
    label: str
    status: str
    implementation_version: str
    metrics: dict[str, float]
    predictions: tuple[Prediction, ...]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ExperimentResult:
    split: dict[str, list[str]]
    models: tuple[ModelResult, ...]

    def as_dict(self):
        return asdict(self)


class ExperimentEngine:
    def capabilities(self):
        rows = []
        for key, model_type in MODEL_TYPES.items():
            available, reason = model_type.availability()
            rows.append(
                {
                    "key": key,
                    "label": model_type.label,
                    "available": available,
                    "reason": reason,
                    "implementation_version": model_type.implementation_version,
                }
            )
        return rows

    def run(
        self,
        snapshot: DatasetSnapshot,
        model_keys,
        validation_months=2,
        test_months=2,
        seed=42,
        simulations=128,
        progress=None,
    ) -> ExperimentResult:
        split = chronological_split(snapshot, validation_months, test_months)
        models = []
        for position, key in enumerate(model_keys):
            model_type = MODEL_TYPES.get(key)
            if model_type is None:
                raise ValueError(f"未知模型：{key}")
            available, reason = model_type.availability()
            if not available:
                raise ValueError(f"模型 {model_type.label} 当前不可用：{reason}")
            if progress:
                progress(position / max(len(model_keys), 1), key)
            model = model_type()
            indices, scores, metadata = model.fit_predict(
                snapshot, split, seed, simulations=simulations
            )
            months = np.asarray([snapshot.records[index]["month"] for index in indices])
            predicted = normalize_monthly_shares(scores, months)
            actual = np.asarray(
                [snapshot.records[index]["share"] for index in indices], dtype=float
            )
            predictions = tuple(
                Prediction(
                    str(month),
                    str(snapshot.records[index]["model"]),
                    float(truth),
                    float(prediction),
                )
                for index, month, truth, prediction in zip(
                    indices, months, actual, predicted, strict=True
                )
            )
            models.append(
                ModelResult(
                    key,
                    model.label,
                    "completed",
                    model.implementation_version,
                    compute_metrics(predicted, actual),
                    predictions,
                    metadata,
                )
            )
        if progress:
            progress(1.0, None)
        return ExperimentResult(
            {
                "train": list(split.train_months),
                "validation": list(split.validation_months),
                "test": list(split.test_months),
            },
            tuple(models),
        )
