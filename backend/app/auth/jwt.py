"""Creating and validating JWT access and refresh tokens (PyJWT, HS256)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

import jwt

from app.config import get_settings
from app.utils.exceptions import UnauthenticatedError
from app.utils.time import utcnow

TokenType = Literal["access", "refresh"]
_REQUIRED_CLAIMS = ["exp", "iat", "iss", "sub", "jti", "type", "tv"]


@dataclass(frozen=True)
class IssuedToken:
    token: str
    jti: str
    expires_at: datetime


@dataclass(frozen=True)
class TokenPayload:
    sub: uuid.UUID
    jti: str
    type: TokenType
    token_version: int
    expires_at: datetime
    family_id: uuid.UUID | None = None


def _encode(claims: dict[str, Any]) -> str:
    s = get_settings()
    return jwt.encode(claims, s.SECRET_KEY, algorithm=s.JWT_ALGORITHM)


def create_access_token(user_id: uuid.UUID, token_version: int) -> IssuedToken:
    s = get_settings()
    now = utcnow()
    expires = now + timedelta(minutes=s.ACCESS_TOKEN_EXPIRE_MINUTES)
    jti = uuid.uuid4().hex
    claims = {
        "iss": s.JWT_ISSUER,
        "sub": str(user_id),
        "type": "access",
        "jti": jti,
        "tv": token_version,
        "iat": now,
        "exp": expires,
    }
    return IssuedToken(_encode(claims), jti, expires)


def create_refresh_token(
    user_id: uuid.UUID, token_version: int, family_id: uuid.UUID
) -> IssuedToken:
    s = get_settings()
    now = utcnow()
    expires = now + timedelta(days=s.REFRESH_TOKEN_EXPIRE_DAYS)
    jti = uuid.uuid4().hex
    claims = {
        "iss": s.JWT_ISSUER,
        "sub": str(user_id),
        "type": "refresh",
        "jti": jti,
        "fam": str(family_id),
        "tv": token_version,
        "iat": now,
        "exp": expires,
    }
    return IssuedToken(_encode(claims), jti, expires)


def decode_token(token: str, expected_type: TokenType) -> TokenPayload:
    """Validate signature, algorithm, issuer, expiry and token type.

    The algorithm list is pinned, which rejects ``alg=none`` and algorithm-confusion attacks.
    """
    s = get_settings()
    try:
        claims = jwt.decode(
            token,
            s.SECRET_KEY,
            algorithms=[s.JWT_ALGORITHM],
            issuer=s.JWT_ISSUER,
            options={"require": _REQUIRED_CLAIMS},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthenticatedError("Token has expired") from exc
    except jwt.PyJWTError as exc:
        raise UnauthenticatedError("Invalid token") from exc

    if claims.get("type") != expected_type:
        raise UnauthenticatedError("Invalid token type")
    try:
        family = claims.get("fam")
        return TokenPayload(
            sub=uuid.UUID(claims["sub"]),
            jti=str(claims["jti"]),
            type=claims["type"],
            token_version=int(claims["tv"]),
            expires_at=datetime.fromtimestamp(int(claims["exp"]), tz=utcnow().tzinfo),
            family_id=uuid.UUID(family) if family else None,
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise UnauthenticatedError("Invalid token") from exc
