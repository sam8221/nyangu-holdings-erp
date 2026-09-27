"""Periodic clean-up. Schedule it daily (cron, Windows Task Scheduler or a container job):

    python -m app.tasks.housekeeping

Removes expired refresh tokens and access-token deny-list entries, spent or expired password
reset tokens, and read notifications older than the retention period.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models.system import Notification, PasswordResetToken
from app.repositories.token_repository import TokenRepository
from app.utils.logging import configure_logging
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

READ_NOTIFICATION_RETENTION_DAYS = 180


@dataclass
class HousekeepingResult:
    refresh_tokens: int
    revoked_access_tokens: int
    password_reset_tokens: int
    notifications: int


def run_housekeeping(db: Session) -> HousekeepingResult:
    refresh, access = TokenRepository(db).purge_expired()
    now = utcnow()
    resets = db.execute(
        delete(PasswordResetToken).where(
            or_(PasswordResetToken.expires_at < now, PasswordResetToken.used_at.is_not(None))
        )
    ).rowcount
    notes = db.execute(
        delete(Notification).where(
            Notification.is_read.is_(True),
            Notification.created_at < now - timedelta(days=READ_NOTIFICATION_RETENTION_DAYS),
        )
    ).rowcount
    db.commit()
    return HousekeepingResult(refresh, access, resets or 0, notes or 0)


def main() -> None:
    configure_logging(get_settings().LOG_LEVEL, get_settings().LOG_FORMAT)
    with SessionLocal() as db:
        result = run_housekeeping(db)
    logger.info("Housekeeping done: %s", result)
    print(result)


if __name__ == "__main__":
    main()
