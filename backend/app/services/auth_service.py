"""Login, token refresh with rotation and reuse detection, logout, password change and reset."""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.auth.hashing import hash_password, needs_rehash, verify_dummy_password, verify_password
from app.auth.jwt import create_access_token, create_refresh_token, decode_token
from app.config import get_settings
from app.models import User
from app.models.system import PasswordResetToken
from app.repositories.token_repository import TokenRepository
from app.repositories.user_repository import UserRepository
from app.services import presenters
from app.services.audit import AuditService
from app.services.email import EmailMessage
from app.utils.exceptions import (
    BadRequestError,
    BusinessRuleError,
    ForbiddenError,
    UnauthenticatedError,
)
from app.utils.time import ensure_aware, utcnow

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS = "Invalid email/username or password"
RESET_REQUESTED = (
    "If an active account uses that email address, a password reset link has been sent to it."
)
INVALID_RESET_TOKEN = "This password reset link is invalid or has expired"


def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def revoke_all_sessions(db: Session, user: User) -> None:
    """Invalidate every access and refresh token the user holds."""
    user.token_version += 1
    TokenRepository(db).revoke_all_refresh_tokens(user.id)


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.tokens = TokenRepository(db)
        self.audit = AuditService(db)
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
            # The identifier is not recorded: users sometimes type a password into it.
            self.audit.log("auth.login_failed", actor=None, summary="Unknown account")
            self.db.commit()
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
            self.audit.log(
                "auth.login_failed",
                actor=user,
                entity_type="user",
                entity_id=user.id,
                summary="Wrong password",
            )
            if user.failed_login_attempts >= self.settings.MAX_FAILED_LOGIN_ATTEMPTS:
                user.locked_until = now + timedelta(minutes=self.settings.ACCOUNT_LOCKOUT_MINUTES)
                user.failed_login_attempts = 0
                logger.warning("Account %s locked after repeated failed logins", user.id)
                self.audit.log(
                    "auth.account_locked",
                    actor=user,
                    entity_type="user",
                    entity_id=user.id,
                    summary=f"Locked for {self.settings.ACCOUNT_LOCKOUT_MINUTES} minutes",
                )
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
        self.audit.log("auth.login", actor=user, entity_type="user", entity_id=user.id)
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
            self.audit.log(
                "auth.refresh_token_reuse",
                actor=user,
                entity_type="user",
                entity_id=user.id,
                summary="Refresh token re-used; all sessions revoked",
            )
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
        self.audit.log(
            "auth.logout_all" if all_devices else "auth.logout",
            actor=user,
            entity_type="user",
            entity_id=user.id,
        )
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
        self.audit.log("auth.password_changed", actor=user, entity_type="user", entity_id=user.id)
        self.db.commit()
        logger.info("Password changed for user %s", user.id)
        return self._public(pair)

    # ------------------------------------------------------------------ forgotten password
    def request_password_reset(self, email: str, *, ip: str | None) -> EmailMessage | None:
        """Create a single-use reset token and return the email to send.

        Returns None when there is no active account for the address. The endpoint responds the
        same way either way, so it does not reveal which addresses have accounts.
        """
        user = self.users.get_by_email(email)
        if user is None or not user.is_active:
            logger.info("Password reset requested for an unknown or inactive address")
            return None

        now = utcnow()
        # Only the newest link works.
        self.db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
            .values(used_at=now)
        )
        token = secrets.token_urlsafe(32)
        minutes = self.settings.PASSWORD_RESET_EXPIRE_MINUTES
        self.db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=_hash_reset_token(token),
                expires_at=now + timedelta(minutes=minutes),
                ip_address=ip,
            )
        )
        self.audit.log(
            "auth.password_reset_requested", actor=user, entity_type="user", entity_id=user.id
        )
        self.db.commit()

        link = f"{self.settings.FRONTEND_URL.rstrip('/')}/reset-password?token={token}"
        body = (
            f"Hello {user.full_name},\n\n"
            f"We received a request to reset the password for your {self.settings.APP_NAME} "
            f"account ({user.username}).\n\n"
            f"Open this link to choose a new password. It expires in {minutes} minutes and can "
            f"only be used once:\n\n{link}\n\n"
            "If you did not ask for this, ignore this email. Your password stays the same."
        )
        return EmailMessage(
            to=user.email, subject=f"Reset your {self.settings.APP_NAME} password", body=body
        )

    def reset_password(self, token: str, new_password: str) -> None:
        stored = self.db.scalars(
            select(PasswordResetToken)
            .where(PasswordResetToken.token_hash == _hash_reset_token(token))
            .with_for_update()
        ).first()
        now = utcnow()
        if stored is None or stored.used_at is not None or ensure_aware(stored.expires_at) <= now:
            raise BadRequestError(INVALID_RESET_TOKEN)

        user = self.users.get_for_update(stored.user_id)
        if user is None or not user.is_active:
            raise BadRequestError(INVALID_RESET_TOKEN)

        stored.used_at = now
        user.password_hash = hash_password(new_password)
        user.password_changed_at = now
        user.failed_login_attempts = 0
        user.locked_until = None
        revoke_all_sessions(self.db, user)
        self.audit.log("auth.password_reset", actor=user, entity_type="user", entity_id=user.id)
        self.db.commit()
        logger.info("Password reset completed for user %s", user.id)
