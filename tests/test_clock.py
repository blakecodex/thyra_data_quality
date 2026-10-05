"""the clock: the two days a year that break an hourly join, and the round trip that catches the hour shift."""

from datetime import date, timedelta

import pytest

from thyra.clock import hour_ending_label, hour_ending_utc, hours_in_local_day, intervals_in_local_day, utc_to_local_day_hour

FALL_BACK = date(2025, 11, 2)
SPRING_FORWARD = date(2026, 3, 8)


def test_fall_back_day_has_25_hours():
    assert hours_in_local_day(FALL_BACK) == 25
    assert intervals_in_local_day(FALL_BACK) == 300


def test_spring_forward_day_has_23_hours():
    assert hours_in_local_day(SPRING_FORWARD) == 23
    assert intervals_in_local_day(SPRING_FORWARD) == 276


def test_a_normal_day_has_24_hours_and_288_intervals():
    assert hours_in_local_day(date(2026, 1, 15)) == 24
    assert intervals_in_local_day(date(2026, 1, 15)) == 288


def test_utc_round_trip_is_exact_on_every_day_of_the_window_and_beyond():
    """every hour of every day maps to utc and back to the same (day, hour); the shift the notebook made cannot survive this."""
    day = date(2025, 10, 1)
    while day <= date(2026, 3, 20):
        for hour in range(1, hours_in_local_day(day) + 1):
            assert utc_to_local_day_hour(hour_ending_utc(day, hour)) == (day, hour)
        day += timedelta(days=1)


def test_the_repeated_hour_is_labelled_the_way_the_publisher_labels_it():
    labels = [hour_ending_label(FALL_BACK, h) for h in range(1, 26)]
    assert labels[:4] == ["01", "02", "02*", "03"]
    assert labels[-1] == "24"
    labels = [hour_ending_label(SPRING_FORWARD, h) for h in range(1, 24)]
    assert labels[:3] == ["01", "03", "04"]


def test_an_hour_the_day_does_not_have_is_refused():
    with pytest.raises(ValueError):
        hour_ending_utc(date(2026, 1, 15), 25)
    with pytest.raises(ValueError):
        hour_ending_utc(SPRING_FORWARD, 24)
