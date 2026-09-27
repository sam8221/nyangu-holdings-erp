"""Role and permission schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.validators import clean_text, normalize_role_name


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    module: str
    action: str
    description: str


class RoleSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    display_name: str


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    display_name: str
    description: str | None
    is_system: bool
    is_active: bool
    permissions: list[str] = Field(description="Permission codes granted by this role")
    user_count: int
    created_at: datetime
    updated_at: datetime


def _clean_codes(codes: list[str] | None) -> list[str] | None:
    if codes is None:
        return None
    return sorted({c.strip().lower() for c in codes if c.strip()})


class RoleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=50, examples=["WAREHOUSE_SUPERVISOR"])
    display_name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    permissions: list[str] = Field(default_factory=list, max_length=500)

    _name = field_validator("name")(normalize_role_name)
    _display = field_validator("display_name")(clean_text)

    @field_validator("permissions")
    @classmethod
    def _perms(cls, v: list[str]) -> list[str]:
        return _clean_codes(v) or []


class RoleUpdate(BaseModel):
    """Only the fields sent are changed. ``permissions`` replaces the whole set when present."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=3, max_length=50)
    display_name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None
    permissions: list[str] | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return normalize_role_name(v) if v is not None else None

    @field_validator("display_name")
    @classmethod
    def _display(cls, v: str | None) -> str | None:
        return clean_text(v) if v is not None else None

    @field_validator("permissions")
    @classmethod
    def _perms(cls, v: list[str] | None) -> list[str] | None:
        return _clean_codes(v)
