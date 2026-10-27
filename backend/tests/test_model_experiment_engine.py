import math

import numpy as np
import pytest

from backend.model_experiments.dataset import build_snapshot, chronological_split
from backend.model_experiments.engine import ExperimentEngine
from backend.model_experiments.features import ordinal_expected_features
from backend.model_experiments.metrics import normalize_monthly_shares
from backend.model_experiments.models import MODEL_TYPES
from backend.model_experiments.models.beast import bspline_basis


def records(months=6):
    rows = []
    for month_index in range(months):
        month = f"2025-{month_index + 1:02d}"
        for model_index, model in enumerate(("甲", "乙", "丙")):
            strength = (model_index + month_index) % 3
            rows.append(
                {
                    "month": month,
                    "model": model,
                    "sales": float((strength + 1) * 10),
                    "share": float(strength + 1) / 6,
                    "pressure": month_index / max(months - 1, 1),
                    "probabilities": {
                        "空间": [1 - strength / 2, strength / 2, 0.0],
                        "续航": [0.0, 1 - strength / 2, strength / 2],
                    },
                }
            )
    return rows


def test_snapshot_and_split_are_stable_and_strictly_chronological():
    snapshot = build_snapshot(
        records(),
        criteria=[
            {"name": "空间", "labels": ["高", "中", "低"]},
            {"name": "续航", "labels": ["高", "中", "低"]},
        ],
        source={"id": "fixture", "name": "测试矩阵", "sha256": "a" * 64},
    )
    split = chronological_split(snapshot, validation_months=1, test_months=2)

    assert split.train_months == ("2025-01", "2025-02", "2025-03")
    assert split.validation_months == ("2025-04",)
    assert split.test_months == ("2025-05", "2025-06")
    assert (
        max(split.train_months) < min(split.validation_months) < min(split.test_months)
    )
    assert len(snapshot.sha256) == 64


def test_ridge_features_use_ordered_semantic_expectation_not_probability_mean():
    matrix, names = ordinal_expected_features(records(1), ("空间", "续航"))

    assert names == ("时间压力", "空间", "续航")
    assert matrix.shape == (3, 3)
    assert len(set(matrix[:, 1])) == 3
    assert not np.allclose(matrix[:, 1], np.mean(matrix[:, 1]))


def test_model_features_remove_time_pressure_from_2026_onward():
    future_records = records(1)
    for row in future_records:
        row['month'] = '2026-01'
        row['pressure'] = 0.9

    matrix, names = ordinal_expected_features(
        future_records, ("空间", "续航")
    )

    assert names[0] == "时间压力"
    assert matrix[:, 0] == pytest.approx(np.zeros(3))


def test_monthly_predictions_are_finite_nonnegative_and_sum_to_one():
    values = normalize_monthly_shares(
        np.array([2.0, -5.0, math.inf, 1.0]),
        np.array(["2025-01", "2025-01", "2025-02", "2025-02"]),
    )

    assert np.isfinite(values).all()
    assert (values >= 0).all()
    assert values[:2].sum() == pytest.approx(1.0)
    assert values[2:].sum() == pytest.approx(1.0)


def test_clamped_bspline_basis_including_right_boundary_is_partition_of_unity():
    basis = bspline_basis(
        np.array([0.0, 0.25, 0.5, 0.75, 1.0]), degree=3, interior_knots=4
    )

    assert basis.shape == (5, 8)
    assert basis.sum(axis=1) == pytest.approx(np.ones(5))
    assert basis[-1, -1] == pytest.approx(1.0)


def test_beast_persists_monthly_diagnostics_with_zero_pressure_from_2026():
    future_rows = records(4)
    for month_index in range(4):
        for row in future_rows[month_index * 3 : (month_index + 1) * 3]:
            row["month"] = f"2026-{month_index + 1:02d}"
            row["pressure"] = 0.9
    snapshot = build_snapshot(
        future_rows,
        criteria=[
            {"name": "空间", "labels": ["高", "中", "低"]},
            {"name": "续航", "labels": ["高", "中", "低"]},
        ],
        source={"id": "future", "name": "2026测试矩阵", "sha256": "b" * 64},
    )

    result = ExperimentEngine().run(
        snapshot,
        model_keys=["beast_mcdm"],
        validation_months=1,
        test_months=1,
        seed=7,
        simulations=16,
    )

    curves = result.models[0].metadata["diagnostic_curves"]
    assert [row["month"] for row in curves["weights"]] == [
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
    ]
    assert [row["month"] for row in curves["rationality"]] == [
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
    ]
    for kind in ("weights", "rationality"):
        for row in curves[kind]:
            assert row["pressure"] == 0.0
            assert set(row["values"]) == {"空间", "续航"}
    assert curves["rationality"][0]["values"] == pytest.approx(
        curves["rationality"][-1]["values"]
    )


@pytest.mark.parametrize(
    "model_key", ["ridge", "random_forest", "xgboost", "lightgbm", "beast_mcdm"]
)
def test_built_in_models_run_end_to_end(model_key):
    available, reason = MODEL_TYPES[model_key].availability()
    if not available:
        pytest.skip(reason)
    snapshot = build_snapshot(
        records(8),
        criteria=[
            {"name": "空间", "labels": ["高", "中", "低"]},
            {"name": "续航", "labels": ["高", "中", "低"]},
        ],
        source={"id": "fixture", "name": "测试矩阵", "sha256": "a" * 64},
    )
    result = ExperimentEngine().run(
        snapshot,
        model_keys=[model_key],
        validation_months=1,
        test_months=2,
        seed=7,
        simulations=64,
    )

    model = result.models[0]
    assert model.key == model_key
    assert model.status == "completed"
    assert set(model.metrics) >= {"RMSE", "WAPE", "R2", "MAE"}
    assert set(model.metadata["validation_metrics"]) >= {"RMSE", "WAPE", "R2", "MAE"}
    assert len(model.predictions) == 6
    for month in ("2025-07", "2025-08"):
        assert sum(
            row.predicted for row in model.predictions if row.month == month
        ) == pytest.approx(1.0)
