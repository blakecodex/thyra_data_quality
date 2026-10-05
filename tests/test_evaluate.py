"""the statistics the gate reads: the band is about the difference, the segments are not hidden by the average and the lag features come from what production saw."""

import numpy as np
import pandas as pd

from thyra.evaluate import backtest, paired_bootstrap, psi
from thyra.features import build_features
from thyra.gate import published
from thyra.model import fit_challenger


def test_bootstrap_band_contains_a_seeded_difference():
    rng = np.random.default_rng(1)
    diff = rng.normal(-0.20, 1.0, size=5000)  # the challenger is better by 0.20 on average, with noise
    lo, hi = paired_bootstrap(diff, seed=1)
    assert lo < -0.20 < hi
    assert hi < 0.0  # and the band says so


def test_bootstrap_band_straddles_zero_when_there_is_no_difference():
    rng = np.random.default_rng(2)
    diff = rng.normal(0.0, 1.0, size=5000)
    lo, hi = paired_bootstrap(diff, seed=2)
    assert lo < 0.0 < hi


def test_psi_reads_near_its_no_change_value_on_two_samples_of_one_distribution():
    rng = np.random.default_rng(3)
    ref, cur = rng.normal(0, 1, 4000), rng.normal(0, 1, 2000)
    value = psi(ref, cur)
    expected = 9 * (1 / 4000 + 1 / 2000)
    assert value < 4 * expected


def test_psi_survives_outliers_and_empty_bins():
    rng = np.random.default_rng(4)
    ref = rng.lognormal(1.0, 0.5, 4000)
    cur = rng.lognormal(1.0, 0.5, 2000)
    cur[:10] = ref.max() * 3  # ten far outliers, the case that makes a naive index fire
    assert psi(ref, cur) < 0.02


def test_a_shift_in_the_feed_moves_psi_past_the_watch_level():
    rng = np.random.default_rng(5)
    ref = rng.normal(20000, 2000, 4000)
    assert psi(ref, ref[:2000] * 1000) > 1.0  # the kilowatt morning


def test_the_clean_challenger_is_better_by_more_than_noise_overall_and_at_the_peak(clean_run):
    rep = clean_run.report
    peak = next(s for s in rep.by_block if s.name == "peak")
    assert rep.overall.hi < 0.0
    assert peak.hi < 0.0
    assert all(s.lo <= 0.0 for s in rep.by_hub)


def test_the_serving_skew_is_visible_in_the_segment_table(clean_run):
    """a feature the serving path never computed: the challenger that won on the backtest loses everywhere once it serves, and the peak band says so."""
    skewed = fit_challenger(clean_run.train, serving_skew=True)
    rep = backtest(clean_run.champion, skewed, clean_run.train, clean_run.test, seed=7)
    peak = next(s for s in rep.by_block if s.name == "peak")
    assert rep.overall.lo > 0.0
    assert peak.lo > 0.0
    assert rep.coverage_challenger < clean_run.report.coverage_challenger


def test_coverage_moves_when_the_band_is_narrowed(clean_run):
    """a 90% band that is squeezed to a 60% band stops covering; that is what the coverage check reads."""
    m = clean_run.challenger
    y = clean_run.test["y"].to_numpy()
    lo, hi = m.band(clean_run.test)
    wide = np.mean((y >= lo) & (y <= hi))
    squeezed = {b: (l * 0.4, h * 0.4) for b, (l, h) in m.bands.items()}
    saved, m.bands = m.bands, squeezed
    try:
        lo2, hi2 = m.band(clean_run.test)
    finally:
        m.bands = saved
    narrow = np.mean((y >= lo2) & (y <= hi2))
    assert wide > 0.85 and narrow < 0.80


def test_lag_features_come_from_the_preliminary_series_by_default(clean_run):
    """the leak: lagging the verified series uses prices the model never had at forecast time. the default is the production path."""
    forecasts = published().forecasts
    prod = build_features(clean_run.final, clean_run.accepted, forecasts)
    leak = build_features(clean_run.final, clean_run.accepted, forecasts, lag_from="verified")
    assert not np.allclose(prod["lag2_spread"].to_numpy(), leak["lag2_spread"].to_numpy())
    default = build_features(clean_run.final, clean_run.accepted, forecasts)
    pd.testing.assert_series_equal(default["lag2_spread"], prod["lag2_spread"])


def test_no_feature_uses_the_day_before_or_the_day_itself(clean_run):
    """at day-ahead close for day d the oldest usable spread is d-2; a lag of one day would be information the model never had."""
    from thyra.features import FIRST_LAG
    assert FIRST_LAG == 2
    df = clean_run.train
    one = df[(df["hub"] == "N.Y.C.")].sort_values(["day", "hour"])
    # the lag2 feature is constant within a hub-day and equals that hub's mean preliminary spread two days earlier
    first_day = one["day"].iloc[0]
    daily = clean_run.accepted.assign(spread=lambda d: d["price_rt"] - d["price_da"]).groupby(["hub", "day"])["spread"].mean()
    from datetime import timedelta
    assert abs(one[one["day"] == first_day]["lag2_spread"].iloc[0] - daily[("N.Y.C.", first_day - timedelta(days=2))]) < 1e-9
