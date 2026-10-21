from __future__ import annotations

import importlib.util
import warnings

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge

from ..features import expanded_probability_features, ordinal_expected_features
from ..metrics import compute_metrics, normalize_monthly_shares


class BaselineModel:
    key = ""
    label = ""
    package = "sklearn"
    implementation_version = "1.0.0"

    @classmethod
    def availability(cls):
        if (
            cls.package == "sklearn"
            or importlib.util.find_spec(cls.package) is not None
        ):
            return True, None
        return False, f"未安装可选依赖 {cls.package}"

    def feature_matrix(self, snapshot):
        return expanded_probability_features(
            snapshot.records, snapshot.criteria, snapshot.levels
        )[0]

    def predict(self, estimator, matrix):
        return estimator.predict(matrix)

    def fit_predict(self, snapshot, split, seed, **_kwargs):
        matrix = self.feature_matrix(snapshot)
        months = np.asarray([row["month"] for row in snapshot.records])
        shares = np.asarray([row["share"] for row in snapshot.records], dtype=float)
        train = split.indices(snapshot.records, "train")
        validation = split.indices(snapshot.records, "validation")
        test = split.indices(snapshot.records, "test")
        estimator = self.estimator(seed)
        estimator.fit(matrix[train], np.log(np.clip(shares[train], 1e-8, 1.0)))
        validation_scores = self.predict(estimator, matrix[validation])
        validation_prediction = normalize_monthly_shares(
            validation_scores, months[validation]
        )
        validation_metrics = compute_metrics(validation_prediction, shares[validation])
        fit_indices = np.concatenate((train, validation))
        estimator.fit(
            matrix[fit_indices], np.log(np.clip(shares[fit_indices], 1e-8, 1.0))
        )
        return (
            test,
            self.predict(estimator, matrix[test]),
            {
                "feature_count": int(matrix.shape[1]),
                "validation_metrics": validation_metrics,
                "refit_months": list(split.train_months + split.validation_months),
            },
        )


class RidgeModel(BaselineModel):
    key = "ridge"
    label = "Ridge 回归"

    def feature_matrix(self, snapshot):
        return ordinal_expected_features(snapshot.records, snapshot.criteria)[0]

    def estimator(self, _seed):
        return Ridge(alpha=1.0)


class RandomForestModel(BaselineModel):
    key = "random_forest"
    label = "随机森林"

    def estimator(self, seed):
        return RandomForestRegressor(
            n_estimators=160, min_samples_leaf=2, random_state=seed, n_jobs=1
        )


class XgboostModel(BaselineModel):
    key = "xgboost"
    label = "XGBoost"
    package = "xgboost"

    def estimator(self, seed):
        from xgboost import XGBRegressor

        return XGBRegressor(
            n_estimators=180,
            max_depth=4,
            learning_rate=0.04,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=seed,
            n_jobs=1,
            objective="reg:squarederror",
        )


class LightGbmModel(BaselineModel):
    key = "lightgbm"
    label = "LightGBM"
    package = "lightgbm"

    def predict(self, estimator, matrix):
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="X does not have valid feature names, but LGBMRegressor was fitted with feature names",
            )
            return estimator.predict(matrix)

    def estimator(self, seed):
        from lightgbm import LGBMRegressor

        return LGBMRegressor(
            n_estimators=180,
            max_depth=5,
            learning_rate=0.04,
            random_state=seed,
            n_jobs=1,
            verbosity=-1,
        )
