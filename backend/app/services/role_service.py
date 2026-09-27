"""Role management and its business rules."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.auth.permissions import SUPER_ADMIN
from app.models import Permission, Role
from app.repositories.role_repository import PermissionRepository, RoleRepository
from app.schemas.rbac import RoleCreate, RoleUpdate
from app.services import presenters
from app.services.audit import AuditService, diff, snapshot
from app.utils.exceptions import (
    BadRequestError,
    BusinessRuleError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)

logger = logging.getLogger(__name__)

_AUDITED_FIELDS = ("name", "display_name", "description", "is_active")


class RoleService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.roles = RoleRepository(db)
        self.permissions = PermissionRepository(db)
        self.audit = AuditService(db)

    def _get_or_404(self, role_id: uuid.UUID) -> Role:
        role = self.roles.get(role_id)
        if role is None:
            raise NotFoundError("Role not found")
        return role

    def _out(self, role: Role) -> dict[str, Any]:
        return presenters.role_out(role, self.roles.user_counts([role.id]).get(role.id, 0))

    def _resolve_permissions(self, codes: list[str]) -> list[Permission]:
        perms = self.permissions.get_by_codes(codes)
        unknown = sorted(set(codes) - {p.code for p in perms})
        if unknown:
            raise BadRequestError(
                "One or more permissions do not exist",
                errors=[
                    {"field": "permissions", "message": f"Unknown permission: {c}"} for c in unknown
                ],
            )
        return perms

    @staticmethod
    def _guard_grant(ctx: AuthContext, codes: set[str]) -> None:
        """You can only grant permissions you already hold."""
        missing = sorted(codes - ctx.permissions) if not ctx.is_super_admin else []
        if missing:
            raise ForbiddenError(
                "You cannot grant permissions you do not have: " + ", ".join(missing)
            )

    # ------------------------------------------------------------------ queries
    def list(self, search: str | None = None) -> list[dict[str, Any]]:
        roles = self.roles.list(search)
        counts = self.roles.user_counts()
        return [presenters.role_out(r, counts.get(r.id, 0)) for r in roles]

    def get(self, role_id: uuid.UUID) -> dict[str, Any]:
        return self._out(self._get_or_404(role_id))

    def list_permissions(self, module: str | None) -> list[Permission]:
        return list(self.permissions.list(module))

    # ------------------------------------------------------------------ commands
    def create(self, ctx: AuthContext, data: RoleCreate) -> dict[str, Any]:
        if self.roles.name_taken(data.name):
            raise ConflictError(
                "A role with this name already exists",
                errors=[{"field": "name", "message": "Role name is already in use"}],
            )
        perms = self._resolve_permissions(data.permissions)
        self._guard_grant(ctx, {p.code for p in perms})
        role = self.roles.add(
            Role(
                name=data.name,
                display_name=data.display_name,
                description=data.description,
                is_system=False,
                is_active=True,
                permissions=perms,
            )
        )
        self.audit.log(
            "roles.create",
            actor=ctx.user,
            entity_type="role",
            entity_id=role.id,
            summary=f"Created role {role.name}",
            changes={
                **snapshot(role, _AUDITED_FIELDS),
                "permissions": sorted(p.code for p in perms),
            },
        )
        self.db.commit()
        self.db.refresh(role)
        logger.info("Role %s created by %s", role.name, ctx.user.id)
        return self._out(role)

    def update(self, ctx: AuthContext, role_id: uuid.UUID, data: RoleUpdate) -> dict[str, Any]:
        role = self._get_or_404(role_id)
        if role.name == SUPER_ADMIN:
            raise BusinessRuleError("The SUPER_ADMIN role cannot be edited")

        changes = data.model_dump(exclude_unset=True)
        before = {
            **snapshot(role, _AUDITED_FIELDS),
            "permissions": sorted(role.permission_codes),
        }
        if "name" in changes and changes["name"] != role.name:
            if role.is_system:
                raise BusinessRuleError("System roles cannot be renamed")
            if changes["name"] is None:
                raise BadRequestError("name cannot be null")
            if self.roles.name_taken(changes["name"], exclude_id=role.id):
                raise ConflictError(
                    "A role with this name already exists",
                    errors=[{"field": "name", "message": "Role name is already in use"}],
                )
            role.name = changes["name"]
        if changes.get("display_name") is not None:
            role.display_name = changes["display_name"]
        if "description" in changes:
            role.description = changes["description"]
        if changes.get("is_active") is not None and changes["is_active"] != role.is_active:
            if role.is_system and not changes["is_active"]:
                raise BusinessRuleError("System roles cannot be deactivated")
            role.is_active = changes["is_active"]
        if changes.get("permissions") is not None:
            perms = self._resolve_permissions(changes["permissions"])
            added = {p.code for p in perms} - role.permission_codes
            self._guard_grant(ctx, added)
            role.permissions = perms

        after = {
            **snapshot(role, _AUDITED_FIELDS),
            "permissions": sorted(p.code for p in role.permissions),
        }
        delta = diff(before, after)
        if delta:
            self.audit.log(
                "roles.update",
                actor=ctx.user,
                entity_type="role",
                entity_id=role.id,
                summary=f"Updated role {role.name}",
                changes=delta,
            )
        self.db.commit()
        self.db.refresh(role)
        logger.info("Role %s updated by %s", role.name, ctx.user.id)
        return self._out(role)

    def delete(self, ctx: AuthContext, role_id: uuid.UUID) -> None:
        role = self._get_or_404(role_id)
        if role.is_system:
            raise BusinessRuleError("System roles cannot be deleted")
        count = self.roles.user_counts([role.id]).get(role.id, 0)
        if count:
            raise BusinessRuleError(
                f"This role is assigned to {count} user(s). Remove it from them before deleting."
            )
        self.audit.log(
            "roles.delete",
            actor=ctx.user,
            entity_type="role",
            entity_id=role.id,
            summary=f"Deleted role {role.name}",
            changes=snapshot(role, _AUDITED_FIELDS),
        )
        self.roles.delete(role)
        self.db.commit()
        logger.info("Role %s deleted by %s", role.name, ctx.user.id)
