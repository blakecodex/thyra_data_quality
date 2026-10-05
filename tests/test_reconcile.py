"""counts and corrections: replay, conflicts, missing hours and the verified price that supersedes the preliminary one exactly once."""

from datetime import date

import pandas as pd
import pytest

from thyra import feeds
from thyra.contract import validate
from thyra.reconcile import apply_revisions, interval_counts, revision_summary, split_duplicates

DAY = date(2025, 11, 20)
FALL_BACK = date(2025, 11, 2)


@pytest.fixture(scope="module")
def pub():
    return feeds.load_snapshot()


def test_replay_twice_is_the_same(pub):
    once, _ = validate(pub.rows)
    twice, _ = validate(feeds.retry(pub.rows, "WEST", DAY))
    clean_once, retries_once, conflicts_once = split_duplicates(once)
    clean_twice, retries_twice, conflicts_twice = split_duplicates(twice)
    assert retries_once == 0 and retries_twice == 24
    assert len(conflicts_twice) == 0
    pd.testing.assert_frame_equal(clean_once, clean_twice)


def test_a_copy_that_disagrees_is_a_conflict_and_the_first_copy_is_kept(pub):
    accepted, _ = validate(feeds.retry_with_conflict(pub.rows, "LONGIL", DAY, hour=17, delta=3.0))
    clean, retries, conflicts = split_duplicates(accepted)
    assert retries == 23
    assert set(map(tuple, conflicts[["hub", "day", "hour"]].drop_duplicates().values)) == {("LONGIL", DAY, 17)}
    original = next(r for r in pub.rows if r["hub"] == "LONGIL" and r["day"] == DAY and r["hour"] == 17)
    kept = clean[(clean.hub == "LONGIL") & (clean.day == DAY) & (clean.hour == 17)].iloc[0]
    assert kept["price_rt"] == original["price_rt"]


def test_a_missing_hour_is_counted_not_averaged_over(pub):
    accepted, _ = validate(feeds.missing_hour(pub.rows, "CENTRL", DAY, 7))
    clean, _, _ = split_duplicates(accepted)
    counts = interval_counts(clean)
    bad = counts[~counts.ok]
    assert len(bad) == 1
    assert (bad.iloc[0]["hub"], bad.iloc[0]["day"], bad.iloc[0]["hours_seen"], bad.iloc[0]["hours_expected"]) == ("CENTRL", DAY, 23, 24)


def test_the_hour_shift_shows_as_a_short_day_and_a_quarantined_hour_zero(pub):
    accepted, held = validate(feeds.shift_hour(pub.rows, "N.Y.C.", FALL_BACK))
    assert held["reason"].tolist() == ["hour_before_day"]
    counts = interval_counts(split_duplicates(accepted)[0])
    bad = counts[~counts.ok].iloc[0]
    assert (bad["hub"], bad["hours_seen"], bad["hours_expected"]) == ("N.Y.C.", 24, 25)


def test_a_whole_day_refused_at_the_door_shows_as_zero_hours(pub):
    accepted, held = validate(feeds.unit_slip(pub.rows, "CAPITL", date(2025, 10, 10)))
    assert held["reason"].value_counts().to_dict() == {"unit_not_usd_mwh": 24}
    counts = interval_counts(split_duplicates(accepted)[0])
    bad = counts[~counts.ok].iloc[0]
    assert (bad["hub"], bad["hours_seen"], bad["hours_expected"]) == ("CAPITL", 0, 24)


def test_verified_supersedes_preliminary_exactly_once(pub):
    accepted, _ = validate(pub.rows)
    clean, _, _ = split_duplicates(accepted)
    rev = pd.DataFrame(pub.revisions)
    once = apply_revisions(clean, rev)
    twice = apply_revisions(once, rev)
    pd.testing.assert_frame_equal(once, twice)
    assert (once["status"] == "verified").all()
    summary = revision_summary(clean, once, tolerance=2.0)
    assert summary["share_off"].mean() < 0.02
    assert summary["mean_abs_diff"].mean() < 0.2


def test_a_revision_for_a_row_that_was_never_published_changes_nothing(pub):
    accepted, _ = validate(pub.rows)
    clean, _, _ = split_duplicates(accepted)
    ghost = pd.DataFrame([dict(pub.rows[0]) | {"day": date(2030, 1, 1), "status": "verified", "price_rt": 999.0}])
    pd.testing.assert_frame_equal(apply_revisions(clean, ghost), clean)
