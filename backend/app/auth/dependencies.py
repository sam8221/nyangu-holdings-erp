"""FastAPI dependencies for authentication and permission checks.

Permissions are read from the database on every request, so role changes apply immediately.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.jwt import TokenPayload, decode_token
from app.auth.permissions import SUPER_ADMIN, Perm
from app.database import get_db
from app.models import User
from app.repositories.token_repository import TokenRepository
from app.repositories.user_repository import UserRepository
from app.utils.exceptions import ForbiddenError, UnauthenticatedError

bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Paste the access_token returned by POST /api/v1/auth/login",
)

DbSession = Annotated[Session, Depends(get_db)]


@dataclass
class AuthContext:
    user: User
    token: TokenPayload
    permissions: frozenset[str] = field(default_factory=frozenset)
    roles: frozenset[str] = field(default_factory=frozenset)

    @property
    def is_super_admin(self) -> bool:
        return SUPER_ADMIN in self.roles

    def has(self, *perms: str) -> bool:
        return self.is_super_admin or all(p in self.permissions for p in perms)

    def has_all(self, perms: set[str] | frozenset[str]) -> bool:
        return self.is_super_admin or set(perms) <= self.permissions


def get_auth_context(
    request: Request,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> AuthContext:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise UnauthenticatedError("Authentication required")

    payload = decode_token(credentials.credentials, "access")

    if TokenRepository(db).is_access_token_revoked(payload.jti):
        raise UnauthenticatedError("Token has been revoked")

    user = UserRepository(db).get(payload.sub)
    if user is None or not user.is_active or user.token_version != payload.token_version:
        raise UnauthenticatedError("Token is no longer valid")

    active_roles = [r for r in user.roles if r.is_active]
    ctx = AuthContext(
        user=user,
        token=payload,
        permissions=frozenset(p.code for r in active_roles for p in r.permissions),
        roles=frozenset(r.name for r in active_roles),
    )
    request.state.user_id = str(user.id)
    return ctx


CurrentAuth = Annotated[AuthContext, Depends(get_auth_context)]


def require_permissions(*perms: Perm | str) -> Callable[..., AuthContext]:
    """Dependency factory: the caller must hold *all* the given permissions.

    SUPER_ADMIN passes every check.
    """
    codes = tuple(str(p) for p in perms)

    def checker(ctx: CurrentAuth) -> AuthContext:
        if not ctx.has(*codes):
            raise ForbiddenError()
        return ctx

    checker.__name__ = f"require_{'_'.join(c.replace('.', '_') for c in codes) or 'auth'}"
    return checker
