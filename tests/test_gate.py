"""the gate: the clean release ships, every seeded defect fails its own check and a retry fails nothing."""

import math

import pytest

from thyra.gate import EXIT_HOLD, EXIT_SHIP, INJECTIONS, build_run, compare, run_gate

# which check each seeded defect must trip. a check that has never been seen to fail tells you nothing.
EXPECTED = {
    "hour_shift": {"hour_count_days_wrong"},
    "conflict": {"duplicate_conflicts"},
    "unit_slip": {"hour_count_days_wrong"},                       # the contract refuses the whole day; the count grid sees a hub-day with zero hours
    "missing_hour": {"hour_count_days_wrong"},
    "fake_hour": set(),                                            # one row is quarantined, well under the rate; the day's count is right
    "load_units": {"psi_max", "band_coverage"},                   # both models are wrecked, so the relative check still passes; the absolute checks catch it
    "skew": {"overall_improvement", "peak_no_regression", "hub_no_regression", "band_coverage"},
}


def _failed(results):
    return {r["check"] for r in results if not r["passed"]}


def test_the_clean_release_passes_every_check(clean_run, suite):
    code, results = run_gate(clean_run, suite)
    assert code == EXIT_SHIP
    assert _failed(results) == set()


def test_every_injection_is_known():
    assert set(EXPECTED) | {"retry"} == set(INJECTIONS)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_each_seeded_defect_fails_exactly_its_checks(name, suite):
    run = build_run(7, [name], suite)
    code, results = run_gate(run, suite)
    assert _failed(results) == EXPECTED[name], (name, _failed(results))
    assert code == (EXIT_SHIP if not EXPECTED[name] else EXIT_HOLD)


def test_a_fake_hour_is_quarantined_with_its_reason(suite):
    run = build_run(7, ["fake_hour"], suite)
    assert run.data["quarantine_reasons"] == {"hour_beyond_day": 1}


def test_a_plain_retry_fails_nothing(suite):
    run = build_run(7, ["retry"], suite)
    code, results = run_gate(run, suite)
    assert code == EXIT_SHIP and run.data["retries_dropped"] == 24 and run.data["conflicting_keys"] == 0


def test_the_three_demo_defects_together_hold_the_release(suite):
    run = build_run(7, ["hour_shift", "conflict", "skew"], suite)
    code, results = run_gate(run, suite)
    assert code == EXIT_HOLD
    assert {"hour_count_days_wrong", "duplicate_conflicts", "peak_no_regression"} <= _failed(results)
    assert run.data["quarantine_reasons"] == {"hour_before_day": 1}


def test_a_check_that_cannot_be_computed_fails():
    """a nan is not a pass. the gate holds when it cannot decide."""
    assert compare(math.nan, "<=", 1.0) is False
    assert compare(None, "==", 0) is False


def test_the_gate_scores_january_before_the_storm_and_keeps_the_storm_for_monitoring(clean_run):
    from datetime import date
    assert clean_run.test["day"].min() == date(2026, 1, 1) and clean_run.test["day"].max() == date(2026, 1, 23)
    assert clean_run.after["day"].min() == date(2026, 1, 24)
