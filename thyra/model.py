"""two small models and a band around each.

ridge regression, closed form, on standardized features. the champion uses the plain
features; the challenger adds the squared price and the peak-by-price term. the band is empirical: the 5th
and 95th percentiles of the training residuals, per hour block, so a 90% band means
what it says on the training window and the gate checks whether it still does on the
test window. the serving skew at the bottom is a seeded defect in the model layer:
a feature the training code computed and the serving path never did, filled with
zero, the kind of slip no unit test on the training code can see.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .features import design

BLOCKS = ("off_peak", "shoulder", "peak")


@dataclass
class Ridge:
    name: str
    interactions: bool
    alpha: float = 1.0
    names: list[str] = field(default_factory=list)
    mean: np.ndarray | None = None
    scale: np.ndarray | None = None
    coef: np.ndarray | None = None
    intercept: float = 0.0
    bands: dict[str, tuple[float, float]] = field(default_factory=dict)
    serving_skew: bool = False

    def fit(self, train: pd.DataFrame) -> "Ridge":
        X, self.names = design(train, self.interactions)
        y = train["y"].to_numpy(float)
        self.mean = X.mean(axis=0)
        self.scale = X.std(axis=0)
        self.scale[self.scale == 0] = 1.0
        Z = (X - self.mean) / self.scale
        # ridge: (z'z + alpha i) beta = z'(y - ybar); the intercept is the target mean on standardized inputs
        self.intercept = float(y.mean())
        A = Z.T @ Z + self.alpha * np.eye(Z.shape[1])
        self.coef = np.linalg.solve(A, Z.T @ (y - self.intercept))
        resid = y - self._predict_matrix(X)
        for block in BLOCKS:
            r = resid[(train["block"] == block).to_numpy()]
            self.bands[block] = (float(np.quantile(r, 0.05)), float(np.quantile(r, 0.95)))
        return self

    def _predict_matrix(self, X: np.ndarray) -> np.ndarray:
        return self.intercept + ((X - self.mean) / self.scale) @ self.coef

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        X, names = design(df, self.interactions)
        if names != self.names:
            raise ValueError("feature schema differs from the one the model was fit on")
        if self.serving_skew and "da_sq" in names:
            # the seeded defect: the serving path never computed the squared price and fills it with zero
            X = X.copy()
            X[:, names.index("da_sq")] = 0.0
        return self._predict_matrix(X)

    def band(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """lower and upper edges of the 90% band around the point forecast, per row."""
        p = self.predict(df)
        lo = np.array([self.bands[b][0] for b in df["block"]])
        hi = np.array([self.bands[b][1] for b in df["block"]])
        return p + lo, p + hi


def fit_champion(train: pd.DataFrame) -> Ridge:
    return Ridge(name="champion", interactions=False, alpha=1.0).fit(train)


def fit_challenger(train: pd.DataFrame, serving_skew: bool = False) -> Ridge:
    m = Ridge(name="challenger", interactions=True, alpha=1.0).fit(train)
    m.serving_skew = serving_skew
    return m
