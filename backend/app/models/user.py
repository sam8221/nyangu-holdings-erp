"""User account model."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.rbac import Role, user_roles


class UserStatus:
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ALL = (ACTIVE, INACTIVE)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="status_valid"),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("username = lower(username)", name="username_lowercase"),
    )

    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=UserStatus.ACTIVE, index=True
    )

    # Bumping token_version invalidates every JWT issued to this user.
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    roles: Mapped[list[Role]] = relationship(
        secondary=user_roles,
        primaryjoin="User.id == user_roles.c.user_id",
        secondaryjoin="Role.id == user_roles.c.role_id",
        lazy="selectin",
        order_by="Role.name",
    )

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

    @property
    def role_names(self) -> set[str]:
        return {r.name for r in self.roles}

    @property
    def permission_codes(self) -> set[str]:
        """Effective permissions: the union over the user's *active* roles."""
        return {p.code for r in self.roles if r.is_active for p in r.permissions}

    def __repr__(self) -> str:
        return f"<User {self.username}>"
