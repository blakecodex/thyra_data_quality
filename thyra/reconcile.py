"""counts and corrections: the checks in the warehouse, after the door and before the features.

three things go wrong between a publisher and a feature table, and none of them raises an
exception. a day is short an hour. a file arrives twice, sometimes with one row changed. the
hourly price a desk saw during the day is not the hourly price settlement uses. each gets a
function here, each returns a frame a person can read, and each is driven by a seeded defect
in the tests.
"""

from __future__ import annotations

import pandas as pd

from .clock import hours_in_local_day
from .contract import HUBS

KEY = ["hub", "day", "hour"]
VALUES = ["price_da", "price_rt"]


def split_duplicates(accepted: pd.DataFrame) -> tuple[pd.DataFrame, int, pd.DataFrame]:
    """one row per key. exact copies are retries and are dropped; copies that disagree are conflicts and are held.

    returns the deduplicated frame, the number of retries dropped and the held conflicts. the
    first copy is kept for a conflicting key and the conflict is reported, so the pipeline keeps
    moving while a person decides. that is a choice, and it is written down.
    """
    if accepted.empty:
        return accepted, 0, accepted.iloc[0:0]
    exact = accepted.drop_duplicates(subset=KEY + VALUES + ["status"])
    retries = len(accepted) - len(exact)
    dup_mask = exact.duplicated(subset=KEY, keep=False)
    conflicts = exact[dup_mask].sort_values(KEY)
    clean = exact.drop_duplicates(subset=KEY, keep="first").sort_values(KEY).reset_index(drop=True)
    return clean, retries, conflicts.reset_index(drop=True)


def interval_counts(rows: pd.DataFrame, hubs: tuple[str, ...] = HUBS) -> pd.DataFrame:
    """per hub per day: hours seen against hours the calendar says the day has.

    the grid is every hub on every day between the first and last day in the feed, not only
    the hub-days that happen to have rows. a hub-day that never arrived, or was refused whole
    at the door, shows up here with zero hours instead of not at all.
    """
    days = pd.date_range(rows["day"].min(), rows["day"].max(), freq="D").date
    grid = pd.MultiIndex.from_product([list(hubs), list(days)], names=["hub", "day"]).to_frame(index=False)
    seen = rows.groupby(["hub", "day"]).size().rename("hours_seen").reset_index()
    out = grid.merge(seen, on=["hub", "day"], how="left").fillna({"hours_seen": 0})
    out["hours_seen"] = out["hours_seen"].astype(int)
    out["hours_expected"] = [hours_in_local_day(d) for d in out["day"]]
    out["ok"] = out["hours_seen"] == out["hours_expected"]
    return out


def apply_revisions(rows: pd.DataFrame, revisions: pd.DataFrame) -> pd.DataFrame:
    """verified rows replace preliminary rows with the same key. applying the same revisions twice changes nothing.

    a revision for a key that was never published is ignored and counted by the caller, because
    a correction to a row that does not exist is its own kind of defect.
    """
    if revisions.empty:
        return rows.copy()
    rev = revisions.drop_duplicates(subset=KEY, keep="last").set_index(KEY)
    out = rows.set_index(KEY)
    hit = out.index.intersection(rev.index)
    out.loc[hit, VALUES + ["status"]] = rev.loc[hit, VALUES + ["status"]].values
    return out.reset_index()


def revision_summary(before: pd.DataFrame, after: pd.DataFrame, tolerance: float = 2.0) -> pd.DataFrame:
    """per hub: the share of hours where the two real-time copies differ by more than the tolerance, and the mean absolute difference."""
    merged = before[KEY + ["price_rt"]].merge(after[KEY + ["price_rt"]], on=KEY, suffixes=("_prelim", "_final")).dropna()
    merged["delta"] = (merged["price_rt_final"] - merged["price_rt_prelim"]).abs()
    merged["off"] = merged["delta"] > tolerance
    out = merged.groupby("hub").agg(share_off=("off", "mean"), mean_abs_diff=("delta", "mean"), hours=("delta", "size"))
    return out.reset_index()
