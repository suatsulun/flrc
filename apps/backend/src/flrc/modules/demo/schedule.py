"""When the shared demo school resets (ADR-052).

The reset day boundary is local midnight in the configured timezone; every
other timestamp the API exposes stays UTC.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from flrc.config import settings


def zone() -> ZoneInfo:
    return ZoneInfo(settings.demo_reset_timezone)


def local_today(now: datetime | None = None) -> date:
    moment = now or datetime.now(UTC)
    return moment.astimezone(zone()).date()


def next_reset_at(now: datetime | None = None) -> datetime:
    """The next local midnight, as an aware UTC datetime."""
    moment = now or datetime.now(UTC)
    local_midnight = datetime.combine(
        local_today(moment) + timedelta(days=1), time.min, tzinfo=zone()
    )
    return local_midnight.astimezone(UTC)


def needs_reset(last_reset_date: str | None, now: datetime | None = None) -> bool:
    """True until a reset has completed on the current local day."""
    return last_reset_date != local_today(now).isoformat()
