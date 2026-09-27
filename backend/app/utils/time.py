"""Time helpers. Everything is stored in UTC; convert to the business timezone only for display."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.config import get_settings


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_local(value: datetime) -> datetime:
    """Convert an aware UTC datetime to the configured business timezone (Africa/Lusaka)."""
    return value.astimezone(ZoneInfo(get_settings().TIMEZONE))


def ensure_aware(value: datetime) -> datetime:
    """Treat naive datetimes as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)
