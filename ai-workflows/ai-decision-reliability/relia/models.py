"""Baseline and candidate response models with held-out calibration."""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer

from . import config as C

_CAT = [C.AUTHORIZED_FEATURES.index("category"), C.AUTHORIZED_FEATURES.index("tenure_bucket")]
_NUM = [i for i in range(len(C.AUTHORIZED_FEATURES)) if i not in _CAT]


def make_baseline(seed):
    pre = ColumnTransformer([("num", StandardScaler(), _NUM),
                             ("cat", OneHotEncoder(handle_unknown="ignore"), _CAT)])
    return make_pipeline(pre, LogisticRegression(C=1.0, max_iter=500, random_state=seed))


def make_candidate(seed):
    return HistGradientBoostingClassifier(max_depth=4, learning_rate=0.06, max_iter=250,
                                          l2_regularization=1.0, categorical_features=_CAT,
                                          random_state=seed)


class CalibratedModel:
    """Model + isotonic calibrator fitted only on the calibration partition."""

    def __init__(self, model):
        self.model = model
        self.cal = IsotonicRegression(y_min=1e-4, y_max=1 - 1e-4, out_of_bounds="clip")

    def fit(self, Xtr, ytr, Xcal, ycal):
        self.model.fit(Xtr, ytr)
        self.cal.fit(self.model.predict_proba(Xcal)[:, 1], ycal)
        return self

    def predict(self, X):
        return self.cal.predict(self.model.predict_proba(X)[:, 1])


def make_ranker(kind, seed):
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.linear_model import Ridge
    if kind == "baseline":
        return make_pipeline(StandardScaler(), Ridge(alpha=1.0, random_state=seed))
    return HistGradientBoostingRegressor(max_depth=4, learning_rate=0.08, max_iter=200, random_state=seed)
