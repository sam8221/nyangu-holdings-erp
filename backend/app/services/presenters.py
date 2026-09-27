"""Convert models into response dictionaries. Keeps sensitive columns out of every response."""

from __future__ import annotations

from typing import Any

from app.auth.permissions import SUPER_ADMIN
from app.models import Role, User
from app.utils.time import utcnow


def role_summary(role: Role) -> dict[str, Any]:
    return {"id": role.id, "name": role.name, "display_name": role.display_name}


def user_out(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "full_name": user.full_name,
        "username": user.username,
        "email": user.email,
        "phone": user.phone,
        "status": user.status,
        "roles": [role_summary(r) for r in user.roles],
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def user_detail(user: User) -> dict[str, Any]:
    return {
        **user_out(user),
        "permissions": sorted(user.permission_codes),
        "is_locked": bool(user.locked_until and user.locked_until > utcnow()),
        "password_changed_at": user.password_changed_at,
    }


def current_user(user: User) -> dict[str, Any]:
    active_roles = [r for r in user.roles if r.is_active]
    return {
        "id": user.id,
        "full_name": user.full_name,
        "username": user.username,
        "email": user.email,
        "phone": user.phone,
        "status": user.status,
        "roles": [role_summary(r) for r in active_roles],
        "permissions": sorted({p.code for r in active_roles for p in r.permissions}),
        "is_super_admin": any(r.name == SUPER_ADMIN for r in active_roles),
    }


def role_out(role: Role, user_count: int) -> dict[str, Any]:
    return {
        "id": role.id,
        "name": role.name,
        "display_name": role.display_name,
        "description": role.description,
        "is_system": role.is_system,
        "is_active": role.is_active,
        "permissions": [p.code for p in role.permissions],
        "user_count": user_count,
        "created_at": role.created_at,
        "updated_at": role.updated_at,
    }
