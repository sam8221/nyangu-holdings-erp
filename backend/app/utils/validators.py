"""Reusable input validators, used by the Pydantic schemas and the seed script."""

from __future__ import annotations

import re

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128

USERNAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{1,48})[a-z0-9]$")
ROLE_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,49}$")
PHONE_RE = re.compile(r"^\+?[0-9 ()-]{7,30}$")


def validate_password_strength(password: str) -> str:
    """Return the password unchanged, or raise ValueError describing every unmet rule."""
    problems: list[str] = []
    if len(password) < PASSWORD_MIN_LENGTH:
        problems.append(f"at least {PASSWORD_MIN_LENGTH} characters")
    if len(password) > PASSWORD_MAX_LENGTH:
        problems.append(f"at most {PASSWORD_MAX_LENGTH} characters")
    if not re.search(r"[A-Z]", password):
        problems.append("an uppercase letter")
    if not re.search(r"[a-z]", password):
        problems.append("a lowercase letter")
    if not re.search(r"[0-9]", password):
        problems.append("a digit")
    if not re.search(r"[^A-Za-z0-9]", password):
        problems.append("a symbol")
    if problems:
        raise ValueError("Password must contain " + ", ".join(problems))
    return password


def normalize_username(value: str) -> str:
    value = value.strip().lower()
    if not USERNAME_RE.match(value):
        raise ValueError(
            "Username must be 3-50 characters: lowercase letters, digits, '.', '_' or '-', "
            "starting and ending with a letter or digit"
        )
    return value


def normalize_role_name(value: str) -> str:
    value = value.strip().upper()
    if not ROLE_NAME_RE.match(value):
        raise ValueError(
            "Role name must be 3-50 characters: uppercase letters, digits or '_', "
            "starting with a letter"
        )
    return value


def normalize_phone(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not PHONE_RE.match(value):
        raise ValueError("Phone number may contain digits, spaces, '+', '-', '(' and ')' only")
    return value


def clean_text(value: str) -> str:
    """Trim and collapse internal whitespace; reject empty strings."""
    value = " ".join(value.split())
    if not value:
        raise ValueError("Must not be blank")
    return value


CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,19}$")


def normalize_code(value: str) -> str:
    """Short reference codes (branches, warehouses, SKUs...): upper case, no spaces."""
    value = value.strip().upper()
    if not CODE_RE.match(value):
        raise ValueError("Code must be 1-20 characters: letters, digits, '-' or '_'")
    return value
