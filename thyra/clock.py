"""the clock, done once and tested, so no one else has to think about it.

the grid operator publishes prices by local day and hour-ending: hour-ending 1
covers midnight to 1 am local, hour-ending 24 ends at midnight. twice a year the
local day is not 24 hours long. on the spring-forward day there are 23 hours, and
on the fall-back day there are 25, with hour-ending 2 occurring twice. a join on
(day, hour) that assumes 24 silently drops or invents an hour of exposure on those
two days, and the error shows up as a one-hour shift that nobody owns.

the rule this module enforces: timestamps in utc inside the pipeline, local labels
only at the edge where a person reads them.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

DEFAULT_TZ = "America/New_York"


def local_midnight_utc(day: date, tz: str = DEFAULT_TZ) -> datetime:
    """the utc instant at which the local day starts."""
    return datetime.combine(day, time(0, 0), tzinfo=ZoneInfo(tz)).astimezone(timezone.utc)


def hours_in_local_day(day: date, tz: str = DEFAULT_TZ) -> int:
    """23 on the spring-forward day, 25 on the fall-back day, 24 otherwise.

    measured in utc: the local day is the span between two local midnights, and
    utc advances uniformly through it, so the span in utc hours is the answer.
    """
    span = local_midnight_utc(day + timedelta(days=1), tz) - local_midnight_utc(day, tz)
    hours = span.total_seconds() / 3600
    if hours != int(hours):
        raise ValueError(f"{day} in {tz} is not a whole number of hours long")
    return int(hours)


def intervals_in_local_day(day: date, tz: str = DEFAULT_TZ, minutes: int = 5) -> int:
    """how many fixed-length intervals the local day holds; 288 on a normal day at five minutes."""
    return hours_in_local_day(day, tz) * 60 // minutes


def hour_ending_utc(day: date, hour: int, tz: str = DEFAULT_TZ) -> datetime:
    """the utc instant at which the k-th hour of the local day ends.

    hours are counted 1..n in order of occurrence, where n is the day's length. on
    the fall-back day hour 2 and hour 3 are both labelled hour-ending 2 by the
    publisher; counting by position removes the ambiguity, and the label is
    recovered with hour_ending_label.
    """
    n = hours_in_local_day(day, tz)
    if not 1 <= hour <= n:
        raise ValueError(f"hour {hour} is outside a {n}-hour day ({day})")
    return local_midnight_utc(day, tz) + timedelta(hours=hour)


def hour_ending_label(day: date, hour: int, tz: str = DEFAULT_TZ) -> str:
    """the publisher's label for the k-th hour: '01'..'24', with '02*' for the repeated hour on the fall-back day."""
    n = hours_in_local_day(day, tz)
    if n == 25:
        if hour <= 2:
            return f"{hour:02d}"
        if hour == 3:
            return "02*"
        return f"{hour - 1:02d}"
    if n == 23:
        # the local clock skips 2 am; hour-ending 3 follows hour-ending 1 directly
        return f"{hour:02d}" if hour == 1 else f"{hour + 1:02d}"
    return f"{hour:02d}"


def utc_to_local_day_hour(ts: datetime, tz: str = DEFAULT_TZ) -> tuple[date, int]:
    """the inverse of hour_ending_utc: which local day and which hour of it ends at this utc instant."""
    if ts.tzinfo is None:
        raise ValueError("a naive timestamp has no clock; pass utc")
    local = ts.astimezone(ZoneInfo(tz))
    # an instant exactly on a local midnight belongs to the day that just ended
    day = local.date() if local.time() != time(0, 0) else local.date() - timedelta(days=1)
    hour = int((ts - local_midnight_utc(day, tz)).total_seconds() // 3600)
    return day, hour
