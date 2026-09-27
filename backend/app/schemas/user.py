"""User schemas. Password hashes and security counters are never part of any response."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.rbac import RoleSummary
from app.utils.validators import (
    clean_text,
    normalize_phone,
    normalize_username,
    validate_password_strength,
)

StatusLiteral = Literal["ACTIVE", "INACTIVE"]


def _lower_email(v: str) -> str:
    return v.strip().lower()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    username: str
    email: str
    phone: str | None
    status: StatusLiteral
    roles: list[RoleSummary]
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UserDetail(UserOut):
    permissions: list[str]
    is_locked: bool
    password_changed_at: datetime | None


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=2, max_length=150, examples=["Mwila Banda"])
    username: str = Field(min_length=3, max_length=50, examples=["mbanda"])
    email: EmailStr = Field(examples=["mwila.banda@nyanguholdings.com"])
    phone: str | None = Field(default=None, max_length=30, examples=["+260 97 1234567"])
    password: str = Field(min_length=1, max_length=128)
    role_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)

    _full_name = field_validator("full_name")(clean_text)
    _username = field_validator("username")(normalize_username)
    _email = field_validator("email")(_lower_email)
    _phone = field_validator("phone")(normalize_phone)
    _password = field_validator("password")(validate_password_strength)


class UserUpdate(BaseModel):
    """Profile fields only. Status, roles and passwords have their own endpoints."""

    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    username: str | None = Field(default=None, min_length=3, max_length=50)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)

    @field_validator("full_name")
    @classmethod
    def _full_name(cls, v: str | None) -> str | None:
        return clean_text(v) if v is not None else None

    @field_validator("username")
    @classmethod
    def _username(cls, v: str | None) -> str | None:
        return normalize_username(v) if v is not None else None

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        return _lower_email(v) if v is not None else None

    _phone = field_validator("phone")(normalize_phone)


class UserStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: StatusLiteral


class UserRolesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_ids: list[uuid.UUID] = Field(max_length=50)


class AdminPasswordReset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_password: str = Field(min_length=1, max_length=128)

    _password = field_validator("new_password")(validate_password_strength)
