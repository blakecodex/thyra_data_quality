"""the contract at the door: each kind of broken row is refused with the reason a person would want to read."""

from datetime import date

from thyra.contract import quarantine_reason, validate

GOOD = dict(hub="N.Y.C.", day=date(2026, 1, 15), hour=1, price_da=30.0, price_rt=32.0, unit="USD/MWh", status="preliminary")


def test_a_good_row_passes():
    assert quarantine_reason(GOOD) is None


def test_a_row_without_a_real_time_price_yet_passes():
    assert quarantine_reason(GOOD | {"price_rt": None}) is None


def test_unit_slip_quarantines():
    assert quarantine_reason(GOOD | {"unit": "USD/kWh"}) == "unit_not_usd_mwh"


def test_an_unknown_zone_quarantines():
    """the four external proxy buses in the publisher's file are not zones; a row from one is refused by name."""
    assert quarantine_reason(GOOD | {"hub": "PJM"}) == "unknown_hub"


def test_hour_25_on_a_normal_day_quarantines_and_passes_on_the_fall_back_day():
    assert quarantine_reason(GOOD | {"hour": 25}) == "hour_beyond_day"
    assert quarantine_reason(GOOD | {"day": date(2025, 11, 2), "hour": 25}) is None


def test_hour_zero_is_the_signature_of_the_hour_shift():
    assert quarantine_reason(GOOD | {"hour": 0}) == "hour_before_day"


def test_a_price_past_the_cap_is_a_parsing_or_unit_error():
    assert quarantine_reason(GOOD | {"price_da": 9000.0}) == "price_out_of_range"
    assert quarantine_reason(GOOD | {"price_rt": -50.0}) is None  # negative prices are real in this market


def test_unknown_fields_and_missing_fields_are_refused():
    assert quarantine_reason(GOOD | {"congestion": 1.0}) == "unexpected_field"
    assert quarantine_reason({k: v for k, v in GOOD.items() if k != "price_da"}) == "missing_field"


def test_validate_keeps_the_payload_of_quarantined_rows():
    accepted, held = validate([GOOD, GOOD | {"unit": "USD/kWh"}])
    assert len(accepted) == 1 and len(held) == 1
    assert held.iloc[0]["reason"] == "unit_not_usd_mwh"
    assert held.iloc[0]["price_da"] == 30.0
