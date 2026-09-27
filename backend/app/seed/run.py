"""Development seed: permissions, system roles and the first Super Administrator.

Usage (from the backend folder):

    python -m app.seed.run

Reads SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD from the environment or .env. If the password is
empty you are prompted for it. Running it again leaves existing data in place.
"""

from __future__ import annotations

import getpass
import re
import sys

from email_validator import EmailNotValidError, validate_email
from sqlalchemy.orm import Session

from app.auth.hashing import hash_password
from app.auth.permissions import SUPER_ADMIN
from app.config import get_settings
from app.database import SessionLocal
from app.models import User, UserStatus
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.seed.catalog import seed_catalog
from app.utils.time import utcnow
from app.utils.validators import validate_password_strength


def _username_from_email(db: Session, email: str) -> str:
    base = re.sub(r"[^a-z0-9._-]", "", email.split("@", 1)[0].lower()).strip("._-")
    base = (base or "admin")[:40]
    if len(base) < 3:
        base = f"{base}admin"
    repo = UserRepository(db)
    candidate, n = base, 1
    while repo.username_taken(candidate):
        n += 1
        candidate = f"{base}{n}"
    return candidate


def _prompt_password() -> str:
    if not sys.stdin.isatty():
        raise SystemExit("SEED_ADMIN_PASSWORD is empty and no terminal is available to prompt.")
    while True:
        first = getpass.getpass("Password for the first administrator: ")
        try:
            validate_password_strength(first)
        except ValueError as exc:
            print(f"  {exc}")
            continue
        if getpass.getpass("Repeat the password: ") != first:
            print("  Passwords do not match.")
            continue
        return first


def seed_admin(db: Session, email: str, password: str | None) -> tuple[User | None, bool]:
    """Create the first SUPER_ADMIN. Returns (user, created)."""
    try:
        email = validate_email(email, check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise SystemExit(f"SEED_ADMIN_EMAIL is not a valid email address: {exc}") from exc

    users = UserRepository(db)
    existing = users.get_by_email(email)
    if existing is not None:
        return existing, False

    password = password or _prompt_password()
    try:
        validate_password_strength(password)
    except ValueError as exc:
        raise SystemExit(f"SEED_ADMIN_PASSWORD is too weak. {exc}") from exc

    role = RoleRepository(db).get_by_name(SUPER_ADMIN)
    assert role is not None, "Run seed_catalog first"
    user = users.add(
        User(
            full_name="System Administrator",
            username=_username_from_email(db, email),
            email=email,
            password_hash=hash_password(password),
            status=UserStatus.ACTIVE,
            password_changed_at=utcnow(),
        )
    )
    users.replace_roles(user, [role.id], assigned_by_id=None)
    return user, True


def main() -> None:
    settings = get_settings()
    with SessionLocal() as db:
        result = seed_catalog(db)
        print(
            f"Permissions: {result.permissions_created} created, "
            f"{result.permissions_updated} updated. System roles: {result.roles_created} created."
            + (" Company profile created." if result.company_created else "")
        )
        if settings.SEED_ADMIN_EMAIL:
            user, created = seed_admin(db, settings.SEED_ADMIN_EMAIL, settings.SEED_ADMIN_PASSWORD)
            if created and user:
                print(f"Super Administrator created: {user.email} (username: {user.username})")
            elif user:
                print(f"Administrator {user.email} already exists; left unchanged.")
        else:
            print("SEED_ADMIN_EMAIL is not set; skipped creating the first administrator.")
        db.commit()


if __name__ == "__main__":
    main()
