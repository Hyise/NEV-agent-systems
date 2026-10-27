from __future__ import annotations

import numpy as np
from scipy.interpolate import BSpline
from scipy.optimize import minimize
from scipy.special import expit, softmax

from ...domain import effective_time_pressure
from ..features import semantic_values
from ..metrics import compute_metrics, normalize_monthly_shares


def bspline_basis(
    x: np.ndarray, degree: int = 3, interior_knots: int = 4
) -> np.ndarray:
    """Clamped B-spline basis with an explicit, correct x=1 boundary."""
    x = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    interior = np.linspace(0.0, 1.0, interior_knots + 2)[1:-1]
    knots = np.concatenate((np.zeros(degree + 1), interior, np.ones(degree + 1)))
    control_count = len(knots) - degree - 1
    result = np.column_stack(
        [
            BSpline(knots, np.eye(control_count)[index], degree, extrapolate=False)(x)
            for index in range(control_count)
        ]
    )
    result[x == 1.0] = 0.0
    result[x == 1.0, -1] = 1.0
    return np.nan_to_num(result)


def _psychological_samples(snapshot, simulations: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    sample_count = max(16, int(simulations))
    result = np.zeros((len(snapshot.records), len(snapshot.criteria)), dtype=float)
    betas = rng.uniform(1e-5, 2.6, sample_count)
    gammas = rng.uniform(1e-5, 0.5, sample_count)
    repetitions = rng.integers(1, 4, sample_count)
    for row_index, row in enumerate(snapshot.records):
        for criterion_index, criterion in enumerate(snapshot.criteria):
            probabilities = np.asarray(row["probabilities"][criterion], dtype=float)
            values = semantic_values(len(probabilities))
            simulation_values = np.zeros(sample_count)
            for sim in range(sample_count):
                draws = []
                tool_probabilities = np.asarray(
                    [1.0, betas[sim] / 3, betas[sim] / 3, betas[sim] / 3]
                )
                tool_probabilities /= tool_probabilities.sum()
                for _ in range(repetitions[sim]):
                    tool = rng.choice(4, p=tool_probabilities)
                    if tool == 0:
                        draws.append(rng.choice(values, p=probabilities))
                    elif tool == 1:
                        draws.append(rng.choice(values))
                    elif tool == 2:
                        supported = values[probabilities > 0]
                        worst = (
                            float(supported.min())
                            if supported.size
                            else float(values.min())
                        )
                        draws.append(
                            worst
                            if worst < -gammas[sim]
                            else rng.choice(values, p=probabilities)
                        )
                    else:
                        reference = rng.choice(values, p=probabilities)
                        draws.append(
                            float(np.ptp(values))
                            if reference >= 0
                            else -float(np.ptp(values))
                        )
                simulation_values[sim] = float(np.mean(draws))
            result[row_index, criterion_index] = float(simulation_values.mean())
    return result


class BeastMcdmModel:
    key = "beast_mcdm"
    label = "BEAST-MCDM（修复版）"
    implementation_version = "1.0.0-numpy"

    @classmethod
    def availability(cls):
        return True, None

    def fit_predict(self, snapshot, split, seed, simulations=128, **_kwargs):
        rows = snapshot.records
        criterion_count = len(snapshot.criteria)
        pressures = np.asarray(
            [effective_time_pressure(row["month"], row.get("pressure")) for row in rows]
        )
        expected = np.zeros((len(rows), criterion_count), dtype=float)
        for row_index, row in enumerate(rows):
            for criterion_index, criterion in enumerate(snapshot.criteria):
                probabilities = np.asarray(row["probabilities"][criterion], dtype=float)
                expected[row_index, criterion_index] = probabilities @ semantic_values(
                    len(probabilities)
                )
        sampled = _psychological_samples(snapshot, simulations, seed)
        basis = bspline_basis(pressures)
        control_grid = np.linspace(-1.0, 1.0, basis.shape[1])
        months = np.asarray([row["month"] for row in rows])
        targets = np.asarray([row["share"] for row in rows], dtype=float)
        train = split.indices(rows, "train")
        validation = split.indices(rows, "validation")
        test = split.indices(rows, "test")

        def predict(parameters, indices):
            importance = softmax(parameters[:criterion_count])
            intercepts = parameters[criterion_count : 2 * criterion_count]
            slopes = parameters[2 * criterion_count : 3 * criterion_count]
            temperature = 1.0 + np.log1p(np.exp(parameters[-1]))
            coefficients = intercepts[:, None] + slopes[:, None] * control_grid[None, :]
            rationality = 0.2 + 0.65 * expit(basis[indices] @ coefficients.T)
            utilities = np.sum(
                importance
                * (
                    rationality * expected[indices]
                    + (1.0 - rationality) * sampled[indices]
                ),
                axis=1,
            )
            return normalize_monthly_shares(temperature * utilities, months[indices])

        initial = np.zeros(criterion_count * 3 + 1, dtype=float)
        initial[-1] = 2.0
        fitted = minimize(
            lambda parameters: (
                float(np.mean((predict(parameters, train) - targets[train]) ** 2))
                + 1e-4 * float(np.mean(parameters**2))
            ),
            initial,
            method="L-BFGS-B",
            options={"maxiter": 80, "ftol": 1e-10},
        )
        importance = softmax(fitted.x[:criterion_count])
        intercepts = fitted.x[criterion_count : 2 * criterion_count]
        slopes = fitted.x[2 * criterion_count : 3 * criterion_count]
        coefficients = intercepts[:, None] + slopes[:, None] * control_grid[None, :]
        diagnostic_curves = {"weights": [], "rationality": []}
        for month in sorted(set(months)):
            index = int(np.flatnonzero(months == month)[0])
            pressure = float(pressures[index])
            rationality = 0.2 + 0.65 * expit(basis[index] @ coefficients.T)
            diagnostic_curves["weights"].append(
                {
                    "month": str(month),
                    "pressure": pressure,
                    "values": {
                        name: float(value)
                        for name, value in zip(
                            snapshot.criteria, importance, strict=True
                        )
                    },
                }
            )
            diagnostic_curves["rationality"].append(
                {
                    "month": str(month),
                    "pressure": pressure,
                    "values": {
                        name: float(value)
                        for name, value in zip(
                            snapshot.criteria, rationality, strict=True
                        )
                    },
                }
            )
        metadata = {
            "simulations": max(16, int(simulations)),
            "optimizer_success": bool(fitted.success),
            "objective": float(fitted.fun),
            "criterion_weights": {
                name: float(value)
                for name, value in zip(snapshot.criteria, importance, strict=True)
            },
            "semantic_scale": "monotonic[-0.5,0.5]",
            "rationality": "clamped-cubic-bspline[0.2,0.85]",
            "diagnostic_curves": diagnostic_curves,
            "validation_metrics": compute_metrics(
                predict(fitted.x, validation), targets[validation]
            ),
        }
        predicted = predict(fitted.x, test)
        return test, np.log(np.clip(predicted, 1e-12, 1.0)), metadata
