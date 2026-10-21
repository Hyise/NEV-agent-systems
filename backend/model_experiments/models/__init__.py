from .baselines import LightGbmModel, RandomForestModel, RidgeModel, XgboostModel
from .beast import BeastMcdmModel

MODEL_TYPES = {
    "ridge": RidgeModel,
    "random_forest": RandomForestModel,
    "xgboost": XgboostModel,
    "lightgbm": LightGbmModel,
    "beast_mcdm": BeastMcdmModel,
}

__all__ = ["MODEL_TYPES"]
