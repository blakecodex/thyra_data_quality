"""features per hub-hour, built only from what was known at day-ahead close.

the target is the spread the desk settles on: the verified real-time price minus the day-ahead
price. the inputs are the day-ahead price, the load forecast issued the day before, the hour
block, the hub, the weekday and lagged spreads. the lags are the trap: at day-ahead close for
day d, the spreads of day d-1 are still being published, so the oldest usable day is d-2, and in
production the lagged spreads are the preliminary ones, because the verified series arrives
later. a backtest that lags the verified series is using information the model never had. the
default here is the production path, and a test pins it.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from .contract import HUBS
from .feeds import clock_hour, hour_block

KEY = ["hub", "day", "hour"]
NUMERIC = ["price_da", "load_forecast_mw", "lag2_spread", "roll7_spread"]
FIRST_LAG, LAST_LAG = 2, 8


def _spread_by_day(rows: pd.DataFrame) -> pd.DataFrame:
    """mean spread per hub per day, the unit the lags are built from."""
    s = rows.dropna(subset=["price_rt"]).assign(spread=lambda d: d["price_rt"] - d["price_da"])
    return s.groupby(["hub", "day"])["spread"].mean().rename("day_spread").reset_index()


def build_features(final_rows: pd.DataFrame, prelim_rows: pd.DataFrame, forecasts: pd.DataFrame, lag_from: str = "preliminary") -> pd.DataFrame:
    """one row per hub-hour with the target and the features. lag_from is 'preliminary' in production; 'verified' is the leak."""
    if lag_from not in ("preliminary", "verified"):
        raise ValueError("lag_from must be 'preliminary' or 'verified'")
    lag_source = prelim_rows if lag_from == "preliminary" else final_rows
    daily = _spread_by_day(lag_source)

    df = final_rows.dropna(subset=["price_rt"]).merge(forecasts, on=KEY, how="inner").sort_values(KEY).reset_index(drop=True)
    df["y"] = df["price_rt"] - df["price_da"]
    df["clock_hour"] = [clock_hour(d, h) for d, h in zip(df["day"], df["hour"])]
    df["block"] = [hour_block(c) for c in df["clock_hour"]]
    df["weekday"] = [1.0 if d.weekday() < 5 else 0.0 for d in df["day"]]

    # lag k: the daily spread of day - k, joined by shifting the daily table forward k days
    for k in range(FIRST_LAG, LAST_LAG + 1):
        shifted = daily.assign(day=daily["day"] + timedelta(days=k)).rename(columns={"day_spread": f"lag{k}"})
        df = df.merge(shifted, on=["hub", "day"], how="left")
    df["lag2_spread"] = df["lag2"]
    df["roll7_spread"] = df[[f"lag{k}" for k in range(FIRST_LAG, LAST_LAG + 1)]].mean(axis=1, skipna=True)
    df = df.drop(columns=[f"lag{k}" for k in range(FIRST_LAG, LAST_LAG + 1)])
    df = df.dropna(subset=["lag2_spread", "roll7_spread", "load_forecast_mw"]).reset_index(drop=True)
    return df


def design(df: pd.DataFrame, interactions: bool = False) -> tuple[np.ndarray, list[str]]:
    """the numeric design matrix: numeric columns, block and hub dummies and, for the challenger, two price terms."""
    cols = {c: df[c].to_numpy(float) for c in NUMERIC}
    cols["weekday"] = df["weekday"].to_numpy(float)
    cols["is_peak"] = (df["block"] == "peak").to_numpy(float)
    cols["is_shoulder"] = (df["block"] == "shoulder").to_numpy(float)
    for hub in HUBS[1:]:
        cols[f"hub_{hub}"] = (df["hub"] == hub).to_numpy(float)
    if interactions:
        # the challenger's two extra terms: spreads widen faster than the price and widen more at the peak
        cols["da_sq"] = cols["price_da"] ** 2
        cols["peak_x_da"] = cols["is_peak"] * cols["price_da"]
    names = list(cols)
    return np.column_stack([cols[n] for n in names]), names
