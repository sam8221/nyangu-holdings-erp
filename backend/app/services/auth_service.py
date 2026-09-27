"""Login, token refresh with rotation and reuse detection, logout and password change."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.auth.hashing import hash_password, needs_rehash, verify_dummy_password, verify_password
from app.auth.jwt import create_access_token, create_refresh_token, decode_token
from app.config import get_settings
from app.models import User
from app.repositories.token_repository import TokenRepository
from app.repositories.user_repository import UserRepository
from app.services import presenters
from app.utils.exceptions import (
    BadRequestError,
    BusinessRuleError,
    ForbiddenError,
    UnauthenticatedError,
)
from app.utils.time import ensure_aware, utcnow

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS = "Invalid email/username or password"


def revoke_all_sessions(db: Session, user: User) -> None:
    """Invalidate every access and refresh token the user holds."""
    user.token_version += 1
    TokenRepository(db).revoke_all_refresh_tokens(user.id)


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.tokens = TokenRepository(db)
        self.settings = get_settings()

    # ------------------------------------------------------------------ helpers
    def _issue_pair(
        self,
        user: User,
        *,
        family_id: uuid.UUID | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        family_id = family_id or uuid.uuid4()
        access = create_access_token(user.id, user.token_version)
        refresh = create_refresh_token(user.id, user.token_version, family_id)
        self.tokens.add_refresh_token(
            user_id=user.id,
            jti=refresh.jti,
            family_id=family_id,
            expires_at=refresh.expires_at,
            ip_address=ip,
            user_agent=user_agent,
        )
        return {
            "access_token": access.token,
            "refresh_token": refresh.token,
            "token_type": "bearer",
            "expires_in": self.settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "refresh_expires_in": self.settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
            "_refresh_jti": refresh.jti,
        }

    @staticmethod
    def _public(pair: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in pair.items() if not k.startswith("_")}

    # ------------------------------------------------------------------ login
    def login(
        self, identifier: str, password: str, *, ip: str | None, user_agent: str | None
    ) -> dict[str, Any]:
        user = self.users.get_by_identifier(identifier)
        if user is None:
            verify_dummy_password(password)  # same work as a real check: no timing oracle
            logger.info("Login failed: unknown account")
            raise UnauthenticatedError(INVALID_CREDENTIALS)

        # Lock the row so concurrent failures are counted correctly.
        user = self.users.get_for_update(user.id)
        assert user is not None
        now = utcnow()

        if user.locked_until and ensure_aware(user.locked_until) > now:
            verify_dummy_password(password)
            self.db.rollback()
            minutes = max(1, int((ensure_aware(user.locked_until) - now).total_seconds() // 60) + 1)
            raise UnauthenticatedError(
                "Account temporarily locked after too many failed attempts. "
                f"Try again in about {minutes} minute(s)."
            )

        if not verify_password(password, user.password_hash):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= self.settings.MAX_FAILED_LOGIN_ATTEMPTS:
                user.locked_until = now + timedelta(minutes=self.settings.ACCOUNT_LOCKOUT_MINUTES)
                user.failed_login_attempts = 0
                logger.warning("Account %s locked after repeated failed logins", user.id)
            self.db.commit()
            raise UnauthenticatedError(INVALID_CREDENTIALS)

        if not user.is_active:
            self.db.rollback()
            raise ForbiddenError("This account has been deactivated. Contact your administrator.")

        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        pair = self._issue_pair(user, ip=ip, user_agent=user_agent)
        self.db.commit()
        self.db.refresh(user)
        logger.info("Login succeeded for user %s", user.id)
        return {**self._public(pair), "user": presenters.current_user(user)}

    # ------------------------------------------------------------------ refresh
    def refresh(self, refresh_token: str, *, ip: str | None, user_agent: str | None) -> dict:
        payload = decode_token(refresh_token, "refresh")
        stored = self.tokens.get_refresh_token_for_update(payload.jti)
        if stored is None or stored.user_id != payload.sub:
            raise UnauthenticatedError("Invalid refresh token")

        user = self.users.get_for_update(stored.user_id)
        if user is None:
            raise UnauthenticatedError("Invalid refresh token")

        if stored.revoked_at is not None:
            # A rotated-out token came back: assume it was stolen and end every session.
            logger.warning(
                "Refresh token reuse detected for user %s; revoking all sessions", user.id
            )
            revoke_all_sessions(self.db, user)
            self.db.commit()
            raise UnauthenticatedError("Refresh token has already been used. Please log in again.")

        if ensure_aware(stored.expires_at) <= utcnow():
            raise UnauthenticatedError("Refresh token has expired")
        if not user.is_active or user.token_version != payload.token_version:
            self.tokens.revoke_refresh_token(stored)
            self.db.commit()
            raise UnauthenticatedError("Session is no longer valid. Please log in again.")

        pair = self._issue_pair(user, family_id=stored.family_id, ip=ip, user_agent=user_agent)
        self.tokens.revoke_refresh_token(stored, replaced_by_jti=pair["_refresh_jti"])
        self.db.commit()
        return self._public(pair)

    # ------------------------------------------------------------------ logout
    def logout(self, ctx: AuthContext, refresh_token: str | None, all_devices: bool) -> None:
        user = ctx.user
        self.tokens.revoke_access_token(ctx.token.jti, user.id, ctx.token.expires_at)

        if refresh_token:
            try:
                payload = decode_token(refresh_token, "refresh")
            except UnauthenticatedError:
                payload = None  # expired or invalid: nothing left to revoke
            if payload and payload.sub == user.id:
                stored = self.tokens.get_refresh_token_for_update(payload.jti)
                if stored and stored.revoked_at is None:
                    self.tokens.revoke_refresh_token(stored)

        if all_devices:
            revoke_all_sessions(self.db, user)
        self.db.commit()

    # ------------------------------------------------------------------ password
    def change_password(
        self,
        ctx: AuthContext,
        current_password: str,
        new_password: str,
        *,
        ip: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        user = self.users.get_for_update(ctx.user.id)
        assert user is not None
        if not verify_password(current_password, user.password_hash):
            raise BadRequestError("Current password is incorrect")
        if verify_password(new_password, user.password_hash):
            raise BusinessRuleError("New password must be different from the current password")

        user.password_hash = hash_password(new_password)
        user.password_changed_at = utcnow()
        revoke_all_sessions(self.db, user)  # ends every other session, including this token
        pair = self._issue_pair(user, ip=ip, user_agent=user_agent)
        self.db.commit()
        logger.info("Password changed for user %s", user.id)
        return self._public(pair)
