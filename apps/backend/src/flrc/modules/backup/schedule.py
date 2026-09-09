"""When the nightly backup runs (ADR-056)."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


def parse_clock(value: str) -> time:
    hour, _, minute = value.strip().partition(":")
    return time(int(hour), int(minute or 0))


def next_run(now: datetime, at: str, timezone: str) -> datetime:
    """The next local wall-clock occurrence of ``at`` after ``now``, as an aware datetime."""
    zone = ZoneInfo(timezone)
    local_now = now.astimezone(zone)
    candidate = datetime.combine(local_now.date(), parse_clock(at), tzinfo=zone)
    if candidate <= local_now:
        candidate = datetime.combine(
            local_now.date() + timedelta(days=1), parse_clock(at), tzinfo=zone
        )
    return candidate


def is_restore_test_day(now: datetime, day: int, timezone: str) -> bool:
    return now.astimezone(ZoneInfo(timezone)).day == day
