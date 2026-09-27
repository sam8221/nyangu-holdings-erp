"""Time helpers. Everything is stored in UTC; convert to the business timezone only for display."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from app.config import get_settings


def utcnow() -> datetime:
    return datetime.now(UTC)


def business_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().TIMEZONE)


def to_local(value: datetime) -> datetime:
    """Convert an aware UTC datetime to the configured business timezone (Africa/Lusaka)."""
    return value.astimezone(business_tz())


def local_today() -> date:
    """Today's date in the business timezone."""
    return datetime.now(business_tz()).date()


def start_of_local_day(value: date) -> datetime:
    """The UTC instant at which ``value`` begins in the business timezone."""
    return datetime.combine(value, time.min, tzinfo=business_tz()).astimezone(UTC)


def ensure_aware(value: datetime) -> datetime:
    """Treat naive datetimes as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)
