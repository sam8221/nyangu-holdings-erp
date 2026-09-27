"""Database queries for users. No business rules here."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, and_, delete, func, insert, or_, select
from sqlalchemy.orm import Session

from app.models import Role, User, UserStatus, user_roles
from app.schemas.common import PageParams


def like_pattern(search: str) -> str:
    """Lower-cased LIKE pattern with %, _ and backslash escaped so they match literally."""
    escaped = search.lower().replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    return f"%{escaped}%"


class UserRepository:
    SORT_FIELDS = {
        "full_name": User.full_name,
        "username": User.username,
        "email": User.email,
        "status": User.status,
        "created_at": User.created_at,
        "last_login_at": User.last_login_at,
    }
    DEFAULT_SORT = ("created_at", "desc")

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, user_id: uuid.UUID) -> User | None:
        return self.db.get(User, user_id)

    def get_for_update(self, user_id: uuid.UUID) -> User | None:
        stmt = (
            select(User)
            .where(User.id == user_id)
            .with_for_update(of=User)
            .execution_options(populate_existing=True)
        )
        return self.db.scalars(stmt).first()

    def get_by_email(self, email: str) -> User | None:
        return self.db.scalars(select(User).where(User.email == email.lower())).first()

    def get_by_username(self, username: str) -> User | None:
        return self.db.scalars(select(User).where(User.username == username.lower())).first()

    def get_by_identifier(self, identifier: str) -> User | None:
        identifier = identifier.strip().lower()
        if "@" in identifier:
            return self.get_by_email(identifier)
        return self.get_by_username(identifier)

    def email_taken(self, email: str, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = select(User.id).where(User.email == email.lower())
        if exclude_id:
            stmt = stmt.where(User.id != exclude_id)
        return self.db.scalar(stmt) is not None

    def username_taken(self, username: str, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = select(User.id).where(User.username == username.lower())
        if exclude_id:
            stmt = stmt.where(User.id != exclude_id)
        return self.db.scalar(stmt) is not None

    def add(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user

    def list(
        self, params: PageParams, *, status: str | None = None, role: str | None = None
    ) -> tuple[Sequence[User], int]:
        stmt: Select[tuple[User]] = select(User)
        if params.search:
            term = like_pattern(params.search)
            stmt = stmt.where(
                or_(
                    func.lower(User.full_name).like(term, escape="\\"),
                    User.email.like(term, escape="\\"),
                    User.username.like(term, escape="\\"),
                )
            )
        if status:
            stmt = stmt.where(User.status == status)
        if role:
            stmt = stmt.where(
                User.id.in_(
                    select(user_roles.c.user_id)
                    .join(Role, Role.id == user_roles.c.role_id)
                    .where(Role.name == role.upper())
                )
            )

        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

        sort_field, sort_order = (
            params.sort_by or self.DEFAULT_SORT[0],
            (params.sort_order or (self.DEFAULT_SORT[1] if not params.sort_by else "asc")),
        )
        column = self.SORT_FIELDS[sort_field]
        ordering = column.asc().nulls_last() if sort_order == "asc" else column.desc().nulls_last()
        stmt = stmt.order_by(ordering, User.id).offset(params.offset).limit(params.page_size)
        return self.db.scalars(stmt).all(), total

    def replace_roles(
        self, user: User, role_ids: Sequence[uuid.UUID], assigned_by_id: uuid.UUID | None
    ) -> None:
        self.db.execute(delete(user_roles).where(user_roles.c.user_id == user.id))
        if role_ids:
            self.db.execute(
                insert(user_roles),
                [
                    {"user_id": user.id, "role_id": rid, "assigned_by_id": assigned_by_id}
                    for rid in dict.fromkeys(role_ids)
                ],
            )
        self.db.flush()
        self.db.expire(user, ["roles"])

    def count_active_with_role(
        self, role_name: str, exclude_user_id: uuid.UUID | None = None
    ) -> int:
        stmt = (
            select(func.count(func.distinct(User.id)))
            .select_from(User)
            .join(user_roles, user_roles.c.user_id == User.id)
            .join(Role, and_(Role.id == user_roles.c.role_id, Role.name == role_name))
            .where(User.status == UserStatus.ACTIVE)
        )
        if exclude_user_id:
            stmt = stmt.where(User.id != exclude_user_id)
        return self.db.scalar(stmt) or 0
