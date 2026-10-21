from __future__ import annotations

import numpy as np


def normalize_monthly_shares(scores: np.ndarray, months: np.ndarray) -> np.ndarray:
    scores = np.asarray(scores, dtype=float).reshape(-1)
    months = np.asarray(months).reshape(-1)
    result = np.zeros_like(scores)
    for month in sorted(set(months.tolist())):
        mask = months == month
        group = np.nan_to_num(scores[mask], nan=0.0, posinf=40.0, neginf=-40.0)
        shifted = np.clip(group - np.max(group), -80.0, 0.0)
        weights = np.exp(shifted)
        total = float(weights.sum())
        result[mask] = (
            weights / total if total > 0 else np.full(mask.sum(), 1.0 / mask.sum())
        )
    return result


def true_monthly_shares(records) -> np.ndarray:
    sales = np.asarray([float(row["sales"]) for row in records], dtype=float)
    months = np.asarray([row["month"] for row in records])
    result = np.zeros_like(sales)
    for month in sorted(set(months.tolist())):
        mask = months == month
        total = sales[mask].sum()
        if total <= 0:
            raise ValueError(f"月份 {month} 的总销量必须大于 0")
        result[mask] = sales[mask] / total
    return result


def compute_metrics(predicted: np.ndarray, actual: np.ndarray) -> dict[str, float]:
    predicted = np.asarray(predicted, dtype=float)
    actual = np.asarray(actual, dtype=float)
    residual = actual - predicted
    denominator = float(np.sum(np.abs(actual)))
    total_variance = float(np.sum((actual - np.mean(actual)) ** 2))
    return {
        "RMSE": float(np.sqrt(np.mean(residual**2))),
        "WAPE": float(np.sum(np.abs(residual)) / max(denominator, 1e-12)),
        "R2": float(1.0 - np.sum(residual**2) / max(total_variance, 1e-12)),
        "MAE": float(np.mean(np.abs(residual))),
    }
