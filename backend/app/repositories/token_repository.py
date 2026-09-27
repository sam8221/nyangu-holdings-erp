"""Database queries for refresh tokens and the access-token deny-list."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import RefreshToken, RevokedAccessToken
from app.utils.time import utcnow


class TokenRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Refresh tokens ---
    def add_refresh_token(
        self,
        *,
        user_id: uuid.UUID,
        jti: str,
        family_id: uuid.UUID,
        expires_at: datetime,
        ip_address: str | None,
        user_agent: str | None,
    ) -> RefreshToken:
        token = RefreshToken(
            user_id=user_id,
            jti=jti,
            family_id=family_id,
            expires_at=expires_at,
            ip_address=(ip_address or None) and ip_address[:45],
            user_agent=(user_agent or None) and user_agent[:255],
        )
        self.db.add(token)
        self.db.flush()
        return token

    def get_refresh_token_for_update(self, jti: str) -> RefreshToken | None:
        return self.db.scalars(
            select(RefreshToken).where(RefreshToken.jti == jti).with_for_update()
        ).first()

    def revoke_refresh_token(self, token: RefreshToken, replaced_by_jti: str | None = None) -> None:
        token.revoked_at = utcnow()
        token.replaced_by_jti = replaced_by_jti
        self.db.flush()

    def revoke_all_refresh_tokens(self, user_id: uuid.UUID) -> None:
        self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )

    # --- Access token deny-list ---
    def revoke_access_token(self, jti: str, user_id: uuid.UUID, expires_at: datetime) -> None:
        self.db.execute(
            pg_insert(RevokedAccessToken)
            .values(jti=jti, user_id=user_id, expires_at=expires_at)
            .on_conflict_do_nothing(index_elements=["jti"])
        )

    def is_access_token_revoked(self, jti: str) -> bool:
        return (
            self.db.scalar(select(RevokedAccessToken.jti).where(RevokedAccessToken.jti == jti))
            is not None
        )

    # --- Housekeeping ---
    def purge_expired(self) -> tuple[int, int]:
        """Delete expired refresh tokens and deny-list entries. Returns (refresh, access) counts."""
        now = utcnow()
        refresh = self.db.execute(delete(RefreshToken).where(RefreshToken.expires_at < now))
        access = self.db.execute(
            delete(RevokedAccessToken).where(RevokedAccessToken.expires_at < now)
        )
        return refresh.rowcount or 0, access.rowcount or 0
