"""User management and its business rules."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.auth.hashing import hash_password
from app.auth.permissions import SUPER_ADMIN, Perm
from app.models import Role, User, UserStatus
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.schemas.common import Page, PageParams
from app.schemas.user import UserCreate, UserUpdate
from app.services import presenters
from app.services.auth_service import revoke_all_sessions
from app.utils.exceptions import (
    BadRequestError,
    BusinessRuleError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.roles = RoleRepository(db)

    # ------------------------------------------------------------------ guards
    def _get_or_404(self, user_id: uuid.UUID, *, for_update: bool = False) -> User:
        user = self.users.get_for_update(user_id) if for_update else self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user

    @staticmethod
    def _guard_super_admin_target(ctx: AuthContext, target: User) -> None:
        if SUPER_ADMIN in target.role_names and not ctx.is_super_admin:
            raise ForbiddenError("Only a Super Administrator can manage a Super Administrator")

    def _guard_last_super_admin(self, target: User) -> None:
        """At least one active SUPER_ADMIN must always remain."""
        if (
            SUPER_ADMIN in target.role_names
            and target.is_active
            and self.users.count_active_with_role(SUPER_ADMIN, exclude_user_id=target.id) == 0
        ):
            raise BusinessRuleError("At least one active Super Administrator must remain")

    def _resolve_roles(self, ctx: AuthContext, role_ids: Sequence[uuid.UUID]) -> list[Role]:
        roles = self.roles.get_many(role_ids)
        found = {r.id for r in roles}
        missing = [str(rid) for rid in dict.fromkeys(role_ids) if rid not in found]
        if missing:
            raise BadRequestError(
                "One or more roles do not exist",
                errors=[{"field": "role_ids", "message": f"Unknown role id: {m}"} for m in missing],
            )
        inactive = [r.name for r in roles if not r.is_active]
        if inactive:
            raise BusinessRuleError(f"Inactive roles cannot be assigned: {', '.join(inactive)}")
        return roles

    @staticmethod
    def _guard_role_grant(ctx: AuthContext, roles: Sequence[Role]) -> None:
        """Stop privilege escalation: you can only hand out what you already hold."""
        if ctx.is_super_admin:
            return
        if any(r.name == SUPER_ADMIN for r in roles):
            raise ForbiddenError("Only a Super Administrator can grant the SUPER_ADMIN role")
        for role in roles:
            if not ctx.has_all(role.permission_codes):
                raise ForbiddenError(
                    f"You cannot assign the role {role.name} because it grants permissions "
                    "you do not have"
                )

    def _check_unique(
        self, *, email: str | None, username: str | None, exclude_id: uuid.UUID | None = None
    ) -> None:
        if email and self.users.email_taken(email, exclude_id):
            raise ConflictError(
                "A user with this email already exists",
                errors=[{"field": "email", "message": "Email is already in use"}],
            )
        if username and self.users.username_taken(username, exclude_id):
            raise ConflictError(
                "A user with this username already exists",
                errors=[{"field": "username", "message": "Username is already in use"}],
            )

    # ------------------------------------------------------------------ queries
    def list(self, params: PageParams, *, status: str | None, role: str | None) -> dict[str, Any]:
        if params.sort_by and params.sort_by not in UserRepository.SORT_FIELDS:
            allowed = ", ".join(sorted(UserRepository.SORT_FIELDS))
            raise BadRequestError(f"Invalid sort field '{params.sort_by}'. Allowed: {allowed}")
        users, total = self.users.list(params, status=status, role=role)
        return Page.build([presenters.user_out(u) for u in users], total, params).model_dump()

    def get(self, user_id: uuid.UUID) -> dict[str, Any]:
        return presenters.user_detail(self._get_or_404(user_id))

    # ------------------------------------------------------------------ commands
    def create(self, ctx: AuthContext, data: UserCreate) -> dict[str, Any]:
        roles: list[Role] = []
        if data.role_ids:
            if not ctx.has(Perm.USERS_ASSIGN_ROLES):
                raise ForbiddenError("Assigning roles requires the users.assign_roles permission")
            roles = self._resolve_roles(ctx, data.role_ids)
            self._guard_role_grant(ctx, roles)

        self._check_unique(email=data.email, username=data.username)
        user = self.users.add(
            User(
                full_name=data.full_name,
                username=data.username,
                email=data.email,
                phone=data.phone,
                password_hash=hash_password(data.password),
                status=UserStatus.ACTIVE,
                password_changed_at=utcnow(),
                created_by_id=ctx.user.id,
            )
        )
        if roles:
            self.users.replace_roles(user, [r.id for r in roles], ctx.user.id)
        self.db.commit()
        self.db.refresh(user)
        logger.info("User %s created by %s", user.id, ctx.user.id)
        return presenters.user_detail(user)

    def update(self, ctx: AuthContext, user_id: uuid.UUID, data: UserUpdate) -> dict[str, Any]:
        user = self._get_or_404(user_id, for_update=True)
        self._guard_super_admin_target(ctx, user)
        changes = data.model_dump(exclude_unset=True)
        for required in ("full_name", "username", "email"):
            if required in changes and changes[required] is None:
                raise BadRequestError(f"{required} cannot be null")
        self._check_unique(
            email=changes.get("email"), username=changes.get("username"), exclude_id=user.id
        )
        for key, value in changes.items():
            setattr(user, key, value)
        self.db.commit()
        self.db.refresh(user)
        return presenters.user_detail(user)

    def set_status(self, ctx: AuthContext, user_id: uuid.UUID, status: str) -> dict[str, Any]:
        user = self._get_or_404(user_id, for_update=True)
        if user.id == ctx.user.id:
            raise BusinessRuleError("You cannot change the status of your own account")
        self._guard_super_admin_target(ctx, user)

        if status == UserStatus.INACTIVE and user.is_active:
            self._guard_last_super_admin(user)
            user.status = UserStatus.INACTIVE
            revoke_all_sessions(self.db, user)
        elif status == UserStatus.ACTIVE and not user.is_active:
            user.status = UserStatus.ACTIVE
            user.failed_login_attempts = 0
            user.locked_until = None
        self.db.commit()
        self.db.refresh(user)
        logger.info("User %s set to %s by %s", user.id, status, ctx.user.id)
        return presenters.user_detail(user)

    def set_roles(
        self, ctx: AuthContext, user_id: uuid.UUID, role_ids: Sequence[uuid.UUID]
    ) -> dict[str, Any]:
        user = self._get_or_404(user_id, for_update=True)
        if user.id == ctx.user.id:
            raise BusinessRuleError("You cannot change your own roles")
        self._guard_super_admin_target(ctx, user)

        new_roles = self._resolve_roles(ctx, role_ids)
        current_ids = {r.id for r in user.roles}
        added = [r for r in new_roles if r.id not in current_ids]
        self._guard_role_grant(ctx, added)

        if SUPER_ADMIN in user.role_names and all(r.name != SUPER_ADMIN for r in new_roles):
            self._guard_last_super_admin(user)

        self.users.replace_roles(user, [r.id for r in new_roles], ctx.user.id)
        self.db.commit()
        self.db.refresh(user)
        logger.info("Roles of user %s replaced by %s", user.id, ctx.user.id)
        return presenters.user_detail(user)

    def reset_password(self, ctx: AuthContext, user_id: uuid.UUID, new_password: str) -> None:
        user = self._get_or_404(user_id, for_update=True)
        if user.id == ctx.user.id:
            raise BusinessRuleError("Use change-password to change your own password")
        self._guard_super_admin_target(ctx, user)

        user.password_hash = hash_password(new_password)
        user.password_changed_at = utcnow()
        user.failed_login_attempts = 0
        user.locked_until = None
        revoke_all_sessions(self.db, user)
        self.db.commit()
        logger.info("Password of user %s reset by %s", user.id, ctx.user.id)
