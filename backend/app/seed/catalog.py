"""Copy the permission catalogue and system roles into the database. Safe to run repeatedly."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.permissions import PERMISSION_DESCRIPTIONS, SYSTEM_ROLES, Perm
from app.config import get_settings
from app.models import Company, Permission, Role
from app.repositories.role_repository import PermissionRepository, RoleRepository

logger = logging.getLogger(__name__)


@dataclass
class CatalogResult:
    permissions_created: int = 0
    permissions_updated: int = 0
    roles_created: int = 0
    company_created: bool = False


def seed_catalog(db: Session) -> CatalogResult:
    """Insert missing permissions and system roles.

    Existing roles are left as they are, so grants an administrator changed are not overwritten.
    Permission descriptions are refreshed from the catalogue.
    """
    result = CatalogResult()
    perm_repo = PermissionRepository(db)
    existing = perm_repo.all_by_code()

    for perm in Perm:
        description = PERMISSION_DESCRIPTIONS[perm]
        row = existing.get(perm.value)
        if row is None:
            row = Permission(
                code=perm.value, module=perm.module, action=perm.action, description=description
            )
            db.add(row)
            existing[perm.value] = row
            result.permissions_created += 1
        elif (row.module, row.action, row.description) != (perm.module, perm.action, description):
            row.module, row.action, row.description = perm.module, perm.action, description
            result.permissions_updated += 1
    db.flush()

    role_repo = RoleRepository(db)
    for spec in SYSTEM_ROLES:
        if role_repo.get_by_name(spec.name) is not None:
            continue
        db.add(
            Role(
                name=spec.name,
                display_name=spec.display_name,
                description=spec.description,
                is_system=True,
                is_active=True,
                permissions=[existing[code] for code in sorted(spec.permissions)],
            )
        )
        result.roles_created += 1
    db.flush()

    if db.scalars(select(Company).limit(1)).first() is None:
        settings = get_settings()
        db.add(
            Company(
                name="Nyangu Holdings",
                country="Zambia",
                currency=settings.DEFAULT_CURRENCY,
                fiscal_year_start_month=1,
            )
        )
        result.company_created = True
        db.flush()
    return result
