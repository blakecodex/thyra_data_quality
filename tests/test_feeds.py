"""the snapshot as the pipeline reads it: positions in the day, the repeated hour, the integration against the publisher's own hourly file."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from thyra import feeds
from thyra.clock import hours_in_local_day
from thyra.contract import HUBS

FALL_BACK = date(2025, 11, 2)


@pytest.fixture(scope="module")
def pub():
    return feeds.load_snapshot()


def test_positions_on_a_normal_day_are_the_clock_hours():
    clock = np.arange(1, 25)
    assert feeds.positions(date(2026, 1, 15), clock, np.zeros(24, dtype=int)).tolist() == list(range(1, 25))


def test_positions_on_the_fall_back_day_split_the_repeated_hour_by_its_two_passes():
    # hourly rows: the publisher lists clock hour 2 twice
    clock = np.array([1, 2, 2] + list(range(3, 25)))
    pos = feeds.positions(FALL_BACK, clock, np.zeros(len(clock), dtype=int))
    assert pos.tolist() == list(range(1, 26))
    # five-minute rows: the minutes restart at the second pass
    clock5 = np.repeat([1, 2, 2, 3], 12)
    minute5 = np.tile(np.arange(5, 61, 5), 4)
    pos5 = feeds.positions(FALL_BACK, clock5, minute5)
    assert pos5[:12].tolist() == [1] * 12 and pos5[12:24].tolist() == [2] * 12 and pos5[24:36].tolist() == [3] * 12 and pos5[36:].tolist() == [4] * 12


def test_positions_on_the_spring_forward_day_close_the_gap():
    clock = np.array([1] + list(range(3, 25)))
    assert feeds.positions(date(2026, 3, 8), clock, np.zeros(len(clock), dtype=int)).tolist() == list(range(1, 24))


def test_the_snapshot_holds_eleven_zones_and_every_hour_of_every_day(pub):
    rows = pd.DataFrame(pub.rows)
    assert set(rows["hub"]) == set(HUBS)
    counts = rows.groupby(["hub", "day"]).size()
    expected = {d: hours_in_local_day(d) for d in rows["day"].unique()}
    assert all(counts[(h, d)] == expected[d] for h, d in counts.index)
    assert counts.xs(FALL_BACK, level="day").eq(25).all()


def test_the_external_proxy_buses_are_left_out_at_load(pub):
    raw = pd.read_csv(feeds.SNAPSHOT / "nyiso_da_zone_hourly.csv.gz")
    assert len(set(raw["zone"]) - set(HUBS)) == 4
    assert set(r["hub"] for r in pub.rows) == set(HUBS)


def test_our_integration_agrees_with_the_publishers_hourly_file(pub):
    """two copies of one number: the mean gap is cents and the hours more than two dollars apart are a fraction of a percent."""
    rows = pd.DataFrame(pub.rows)[["hub", "day", "hour", "price_rt"]]
    rev = pd.DataFrame(pub.revisions)[["hub", "day", "hour", "price_rt"]]
    m = rows.merge(rev, on=["hub", "day", "hour"], suffixes=("_ours", "_theirs"))
    gap = (m["price_rt_ours"] - m["price_rt_theirs"]).abs()
    assert len(m) == len(rows)
    assert gap.mean() < 0.2
    assert (gap > 2.0).mean() < 0.02


def test_the_load_forecast_is_the_vintage_issued_the_day_before(pub):
    fc = pub.forecasts
    assert set(fc["hub"]) == set(HUBS)
    assert fc[(fc["hub"] == "N.Y.C.") & (fc["day"] == FALL_BACK)].shape[0] == 25
    assert fc["day"].min() == date(2025, 10, 2)  # the october 1 vintage was issued on september 30, outside the snapshot
