from __future__ import annotations

import numpy as np

from ..domain import effective_time_pressure


def semantic_values(level_count: int) -> np.ndarray:
    if level_count < 2:
        raise ValueError("每项准则至少需要两个有序等级")
    return np.linspace(0.5, -0.5, level_count, dtype=float)


def ordinal_expected_features(records, criteria: tuple[str, ...]):
    rows = []
    for row in records:
        values = [effective_time_pressure(row["month"], row.get("pressure"))]
        for criterion in criteria:
            probabilities = np.asarray(row["probabilities"][criterion], dtype=float)
            values.append(float(probabilities @ semantic_values(len(probabilities))))
        rows.append(values)
    return np.asarray(rows, dtype=float), ("时间压力", *criteria)


def expanded_probability_features(
    records, criteria: tuple[str, ...], levels: tuple[int, ...]
):
    rows = []
    for row in records:
        values = [effective_time_pressure(row["month"], row.get("pressure"))]
        for criterion, level_count in zip(criteria, levels, strict=True):
            probabilities = list(row["probabilities"][criterion])
            values.extend(float(value) for value in probabilities[:level_count])
            values.extend([0.0] * max(0, level_count - len(probabilities)))
        rows.append(values)
    names = ["时间压力"]
    for criterion, level_count in zip(criteria, levels, strict=True):
        names.extend(f"{criterion}_L{index}" for index in range(level_count))
    return np.asarray(rows, dtype=float), tuple(names)
