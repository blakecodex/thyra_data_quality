"""the snapshot, read the way the platform read its feeds: by local day and position in the day.

the data is public nyiso zonal pricing, pulled once by pull_snapshot.py and committed under
data/snapshot. four files matter here:

  nyiso_da_zone_hourly              day-ahead price per zone and hour, local clock time, hour-beginning labels
  nyiso_rt_zone_5min                real-time price per zone about every five minutes, local clock time, interval-end stamps
  nyiso_rt_zone_hourly_integrated   the publisher's own time-weighted hourly real-time price, the settlement series
  nyiso_load_forecast_zone_hourly   the zonal load forecast, one file per issue day, six days ahead

the eleven load zones stand in for hubs; the four external proxy buses in the same files are not
zones and are left out at load. the preliminary real-time price is our own time-weighted integration
of the five-minute series to the hour, which is what a desk sees during the day; the verified price
is the publisher's integrated hourly file, which arrives later.

the clock is the trap. the files carry local clock labels with no time zone, and the fall-back day in
the window, 2025-11-02, has 25 hours: the day-ahead file lists 01:00 twice and the five-minute file
runs 01:05 to 02:00 twice. hours are therefore counted by position in the day, the repeated hour by
the order of the two passes, and the clock module turns positions into utc.

the injectors at the bottom are the defects the checks exist to catch; each is used by a test and by
the demo. they change copies and leave the snapshot alone.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .clock import hour_ending_label, hours_in_local_day
from .contract import HUBS, UNIT

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "data" / "snapshot"
HOURLY_STAMP = "%m/%d/%Y %H:%M"
FIVE_MIN_STAMP = "%m/%d/%Y %H:%M:%S"

# off-peak, shoulder and peak by clock hour-ending; the money is in the peak
PEAK = set(range(12, 20))
SHOULDER = set(range(8, 12)) | set(range(20, 23))


def hour_block(clock_hour: int) -> str:
    if clock_hour in PEAK:
        return "peak"
    if clock_hour in SHOULDER:
        return "shoulder"
    return "off_peak"


def clock_hour(day: date, hour: int) -> int:
    """the clock hour a position in the local day corresponds to; the repeated hour on the fall-back day maps to 2."""
    return int(hour_ending_label(day, hour).rstrip("*"))


@dataclass
class Published:
    rows: list[dict]           # preliminary rows, as the contract expects them
    revisions: list[dict]      # verified rows for every hour the publisher's hourly file covers
    forecasts: pd.DataFrame    # per hub, day, hour: the load forecast issued the day before
    start: date
    end: date
    manifest: dict


def _read(name: str, snapshot: Path) -> pd.DataFrame | None:
    path = snapshot / f"{name}.csv.gz"
    if not path.exists():
        return None
    return pd.read_csv(path, compression="gzip")


def positions(day: date, clock: np.ndarray, minute: np.ndarray) -> np.ndarray:
    """clock hour-endings in publication order to positions 1..n in the local day.

    on a 24-hour day the position is the clock hour. on the 25-hour day clock hour 2 occurs twice:
    the first pass keeps position 2, the second pass takes position 3 and every later hour moves up
    one; the second pass starts where the minutes within the hour stop increasing, or at the second
    row when the rows are hourly. on the 23-hour day clock hour 2 does not occur and every hour from
    3 on moves down one.
    """
    n = hours_in_local_day(day)
    clock = np.asarray(clock, dtype=int)
    if n == 24:
        return clock.copy()
    if n == 23:
        return np.where(clock >= 3, clock - 1, clock)
    pos = np.where(clock >= 3, clock + 1, clock)
    idx = np.flatnonzero(clock == 2)
    if len(idx) > 1:
        m = np.asarray(minute, dtype=int)[idx]
        restart = next((k for k in range(1, len(idx)) if m[k] <= m[k - 1]), 1)
        pos[idx[restart:]] = 3
    return pos


def _hourly_by_position(df: pd.DataFrame, stamp_col: str = "time_stamp") -> pd.DataFrame:
    """hourly rows per zone and local day, numbered 1..n in publication order. the labels are hour-beginning."""
    out = df.copy()
    out["day"] = pd.to_datetime(out["file_day"]).dt.date
    ts = pd.to_datetime(out[stamp_col], format=HOURLY_STAMP)
    out["clock"] = ts.dt.hour + 1
    out["minute"] = 0
    out = out.sort_values(["zone", "day"], kind="stable")  # stable: publication order survives within a zone-day
    out["hour"] = 0
    for (_, day), g in out.groupby(["zone", "day"], sort=False):
        out.loc[g.index, "hour"] = positions(day, g["clock"].to_numpy(), g["minute"].to_numpy())
    return out


def integrate_rt(rt: pd.DataFrame) -> pd.DataFrame:
    """the five-minute series integrated to the hour the way the publisher does it: weighted by interval length.

    stamps mark the end of an interval, so 00:05 is the first interval of hour-ending 1 and the next
    day's 00:00 closes hour-ending 24. the run is not always five minutes: the dispatch runs again when
    it has to, so each interval is weighted by the minutes since the previous stamp.
    """
    df = rt[["file_day", "time_stamp", "zone", "lbmp"]].copy()
    df["day"] = pd.to_datetime(df["file_day"]).dt.date
    ts = pd.to_datetime(df["time_stamp"], format=FIVE_MIN_STAMP)
    day_start = pd.to_datetime(df["file_day"])
    minutes = ((ts - day_start).dt.total_seconds() / 60).round().astype(int)
    df["clock"] = np.ceil(minutes / 60).astype(int).clip(lower=1)
    df["minute"] = minutes % 60
    df.loc[df["minute"] == 0, "minute"] = 60
    df["minutes"] = minutes
    df = df.sort_values(["zone", "day"], kind="stable")
    df["hour"] = 0
    df["weight"] = 0.0
    for (_, day), g in df.groupby(["zone", "day"], sort=False):
        mins = g["minutes"].to_numpy()
        prev = np.concatenate([[0], mins[:-1]])
        # the second pass of the repeated hour on the fall-back day restarts the minute count; weight it from its own start
        w = mins - prev
        w = np.where(w <= 0, 5, w).astype(float)
        df.loc[g.index, "weight"] = w
        df.loc[g.index, "hour"] = positions(day, g["clock"].to_numpy(), g["minute"].to_numpy())
    df["wp"] = df["weight"] * df["lbmp"]
    agg = df.groupby(["zone", "day", "hour"]).agg(wp=("wp", "sum"), w=("weight", "sum"), intervals=("lbmp", "size")).reset_index()
    agg["price_rt"] = agg["wp"] / agg["w"]
    return agg[["zone", "day", "hour", "price_rt", "intervals"]]


def load_forecast_vintage(fc: pd.DataFrame) -> pd.DataFrame:
    """the load forecast for day d as issued on day d-1, per zone and position in the day."""
    df = fc.copy()
    stamp_col = next((c for c in df.columns if c.strip().lower().startswith("time stamp")), None)
    if stamp_col is None:
        raise ValueError("the load forecast file has no time stamp column")
    df["issued"] = pd.to_datetime(df["file_day"]).dt.date
    ts = pd.to_datetime(df[stamp_col], format=HOURLY_STAMP)
    df["day"] = ts.dt.date
    df["clock"] = ts.dt.hour + 1
    df = df[df["day"] == df["issued"] + timedelta(days=1)].copy()
    zone_cols = {c: c.strip().upper() for c in df.columns if c.strip().upper() in HUBS}
    df["hour"] = 0
    for day, g in df.groupby("day", sort=False):
        df.loc[g.index, "hour"] = positions(day, g["clock"].to_numpy(), np.zeros(len(g), dtype=int))
    long = df.melt(id_vars=["day", "hour"], value_vars=list(zone_cols), var_name="zone", value_name="load_forecast_mw")
    long["hub"] = long["zone"].map(zone_cols)
    long["load_forecast_mw"] = pd.to_numeric(long["load_forecast_mw"], errors="coerce")
    return long[["hub", "day", "hour", "load_forecast_mw"]].dropna().sort_values(["hub", "day", "hour"]).reset_index(drop=True)


def load_snapshot(snapshot: Path | str = SNAPSHOT) -> Published:
    snapshot = Path(snapshot)
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8")) if (snapshot / "manifest.json").exists() else {}
    da = _read("nyiso_da_zone_hourly", snapshot)
    rt = _read("nyiso_rt_zone_5min", snapshot)
    hourly = _read("nyiso_rt_zone_hourly_integrated", snapshot)
    fc = _read("nyiso_load_forecast_zone_hourly", snapshot)
    if da is None or rt is None or hourly is None:
        raise FileNotFoundError(f"the snapshot under {snapshot} needs the day-ahead, five-minute and integrated hourly files; run pull_snapshot.py")

    da = _hourly_by_position(da[da["zone"].isin(HUBS)])
    prelim = integrate_rt(rt[rt["zone"].isin(HUBS)])
    verified = _hourly_by_position(hourly[hourly["zone"].isin(HUBS)])

    base = da[["zone", "day", "hour", "lbmp"]].rename(columns={"zone": "hub", "lbmp": "price_da"})
    base = base.merge(prelim.rename(columns={"zone": "hub"})[["hub", "day", "hour", "price_rt"]], on=["hub", "day", "hour"], how="left")
    rows = []
    for r in base.itertuples(index=False):
        price_rt = None if pd.isna(r.price_rt) else round(float(r.price_rt), 2)
        rows.append({"hub": r.hub, "day": r.day, "hour": int(r.hour), "price_da": round(float(r.price_da), 2), "price_rt": price_rt, "unit": UNIT, "status": "preliminary"})

    ver = verified[["zone", "day", "hour", "lbmp"]].rename(columns={"zone": "hub", "lbmp": "price_rt"})
    ver = ver.merge(base[["hub", "day", "hour", "price_da"]], on=["hub", "day", "hour"], how="inner")
    revisions = [
        {"hub": r.hub, "day": r.day, "hour": int(r.hour), "price_da": round(float(r.price_da), 2), "price_rt": round(float(r.price_rt), 2), "unit": UNIT, "status": "verified"}
        for r in ver.itertuples(index=False)
    ]

    forecasts = load_forecast_vintage(fc) if fc is not None else pd.DataFrame(columns=["hub", "day", "hour", "load_forecast_mw"])
    start, end = base["day"].min(), base["day"].max()
    return Published(rows=rows, revisions=revisions, forecasts=forecasts, start=start, end=end, manifest=manifest)


# ---- injectors. each returns a new list and leaves the input alone.

def shift_hour(rows: list[dict], hub: str, day: date) -> list[dict]:
    """the utc-versus-local mistake: every hour of one hub-day is labelled one earlier. hour 0 appears; the last hour vanishes."""
    return [r | {"hour": r["hour"] - 1} if (r["hub"] == hub and r["day"] == day) else r for r in rows]


def retry(rows: list[dict], hub: str, day: date) -> list[dict]:
    """a file loaded twice: exact copies of one hub-day appended."""
    return rows + [dict(r) for r in rows if r["hub"] == hub and r["day"] == day]


def retry_with_conflict(rows: list[dict], hub: str, day: date, hour: int = 17, delta: float = 3.0) -> list[dict]:
    """a file loaded twice, and one row in the second copy disagrees with the first."""
    copies = [dict(r) for r in rows if r["hub"] == hub and r["day"] == day]
    for r in copies:
        if r["hour"] == hour and r["price_rt"] is not None:
            r["price_rt"] = round(r["price_rt"] + delta, 2)
    return rows + copies


def missing_hour(rows: list[dict], hub: str, day: date, hour: int) -> list[dict]:
    """one hour never arrives."""
    return [r for r in rows if not (r["hub"] == hub and r["day"] == day and r["hour"] == hour)]


def unit_slip(rows: list[dict], hub: str, day: date) -> list[dict]:
    """the publisher labels one hub-day in $/kwh. the contract refuses it; the count check notices the hole."""
    return [r | {"unit": "USD/kWh"} if (r["hub"] == hub and r["day"] == day) else r for r in rows]


def fake_hour(rows: list[dict], hub: str, day: date) -> list[dict]:
    """an hour the day does not have."""
    n = hours_in_local_day(day)
    extra = next(dict(r) for r in rows if r["hub"] == hub and r["day"] == day)
    extra["hour"] = n + 1
    return rows + [extra]


def forecast_unit_change(forecasts: pd.DataFrame, from_day: date) -> pd.DataFrame:
    """the load forecast feed switches to kilowatts one morning and nobody announces it. the model sees numbers a thousand times too large."""
    out = forecasts.copy()
    late = out["day"] >= from_day
    out.loc[late, "load_forecast_mw"] = out.loc[late, "load_forecast_mw"] * 1000.0
    return out
