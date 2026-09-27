"""In-app notifications: approval requests, decisions and stock alerts."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.auth.permissions import SUPER_ADMIN
from app.models import Permission, Role, User, UserStatus, role_permissions, user_roles
from app.models.system import Notification
from app.repositories.query import paginate
from app.schemas.common import Page, PageParams
from app.utils.exceptions import NotFoundError
from app.utils.time import utcnow

CATEGORIES = ("INFO", "APPROVAL", "ALERT", "SUCCESS")


class NotificationService:
    SORT_FIELDS = {"created_at": Notification.created_at}

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ sending
    def notify(
        self,
        user_ids: Iterable[uuid.UUID],
        title: str,
        message: str,
        *,
        category: str = "INFO",
        entity_type: str | None = None,
        entity_id: Any = None,
        exclude_user_id: uuid.UUID | None = None,
    ) -> int:
        recipients = [uid for uid in dict.fromkeys(user_ids) if uid and uid != exclude_user_id]
        for uid in recipients:
            self.db.add(
                Notification(
                    user_id=uid,
                    title=title[:200],
                    message=message,
                    category=category,
                    entity_type=entity_type,
                    entity_id=str(entity_id) if entity_id is not None else None,
                )
            )
        return len(recipients)

    def users_with_permission(self, code: str) -> list[uuid.UUID]:
        """Active users holding ``code`` through an active role, plus every Super Administrator."""
        holders = (
            select(user_roles.c.user_id)
            .join(Role, Role.id == user_roles.c.role_id)
            .outerjoin(role_permissions, role_permissions.c.role_id == Role.id)
            .outerjoin(Permission, Permission.id == role_permissions.c.permission_id)
            .where(Role.is_active.is_(True), or_(Permission.code == code, Role.name == SUPER_ADMIN))
        )
        stmt = select(User.id).where(User.status == UserStatus.ACTIVE, User.id.in_(holders))
        return list(self.db.scalars(stmt).all())

    def notify_permission(
        self,
        code: str,
        title: str,
        message: str,
        **kwargs: Any,
    ) -> int:
        return self.notify(self.users_with_permission(code), title, message, **kwargs)

    # ------------------------------------------------------------------ reading
    def list_for_user(
        self, user_id: uuid.UUID, params: PageParams, unread_only: bool
    ) -> dict[str, Any]:
        stmt = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            stmt = stmt.where(Notification.is_read.is_(False))
        items, total = paginate(
            self.db, stmt, params, self.SORT_FIELDS, ("created_at", "desc"), Notification.id
        )
        return Page.build(items, total, params).model_dump()

    def unread_count(self, user_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(
            Notification.user_id == user_id, Notification.is_read.is_(False)
        )
        return self.db.scalar(stmt) or 0

    def mark_read(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification:
        note = self.db.get(Notification, notification_id)
        if note is None or note.user_id != user_id:  # never reveal other users' notifications
            raise NotFoundError("Notification not found")
        if not note.is_read:
            note.is_read = True
            note.read_at = utcnow()
            self.db.commit()
        return note

    def mark_all_read(self, user_id: uuid.UUID) -> int:
        result = self.db.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
            .values(is_read=True, read_at=utcnow())
        )
        self.db.commit()
        return result.rowcount or 0
