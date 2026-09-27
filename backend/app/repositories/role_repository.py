"""Database queries for roles and permissions. No business rules here."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Permission, Role, user_roles
from app.repositories.query import like_pattern


class RoleRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, role_id: uuid.UUID) -> Role | None:
        return self.db.get(Role, role_id)

    def get_by_name(self, name: str) -> Role | None:
        return self.db.scalars(select(Role).where(Role.name == name.upper())).first()

    def get_many(self, role_ids: Iterable[uuid.UUID]) -> list[Role]:
        ids = list(dict.fromkeys(role_ids))
        if not ids:
            return []
        return list(self.db.scalars(select(Role).where(Role.id.in_(ids))).all())

    def name_taken(self, name: str, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = select(Role.id).where(Role.name == name.upper())
        if exclude_id:
            stmt = stmt.where(Role.id != exclude_id)
        return self.db.scalar(stmt) is not None

    def list(self, search: str | None = None) -> Sequence[Role]:
        stmt = select(Role)
        if search:
            term = like_pattern(search)
            stmt = stmt.where(
                func.lower(Role.name).like(term, escape="\\")
                | func.lower(Role.display_name).like(term, escape="\\")
            )
        return self.db.scalars(stmt.order_by(Role.is_system.desc(), Role.name)).all()

    def user_counts(self, role_ids: Iterable[uuid.UUID] | None = None) -> dict[uuid.UUID, int]:
        stmt = select(user_roles.c.role_id, func.count()).group_by(user_roles.c.role_id)
        if role_ids is not None:
            stmt = stmt.where(user_roles.c.role_id.in_(list(role_ids)))
        return {rid: count for rid, count in self.db.execute(stmt).all()}

    def add(self, role: Role) -> Role:
        self.db.add(role)
        self.db.flush()
        return role

    def delete(self, role: Role) -> None:
        self.db.delete(role)
        self.db.flush()


class PermissionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self, module: str | None = None) -> Sequence[Permission]:
        stmt = select(Permission)
        if module:
            stmt = stmt.where(Permission.module == module.lower())
        return self.db.scalars(stmt.order_by(Permission.module, Permission.code)).all()

    def get_by_codes(self, codes: Iterable[str]) -> list[Permission]:
        codes = list(dict.fromkeys(codes))
        if not codes:
            return []
        return list(self.db.scalars(select(Permission).where(Permission.code.in_(codes))).all())

    def all_by_code(self) -> dict[str, Permission]:
        return {p.code: p for p in self.db.scalars(select(Permission)).all()}
