"""Authentication request and response schemas."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.rbac import RoleSummary
from app.utils.validators import validate_password_strength


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: str = Field(
        min_length=1,
        max_length=255,
        description="Email address or username",
        examples=["admin@nyanguholdings.com"],
    )
    password: str = Field(min_length=1, max_length=128)

    @field_validator("identifier")
    @classmethod
    def _normalise(cls, v: str) -> str:
        return v.strip().lower()


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=1, max_length=4096)


class LogoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str | None = Field(default=None, max_length=4096)
    all_devices: bool = False


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)

    _new = field_validator("new_password")(validate_password_strength)


class CurrentUser(BaseModel):
    id: uuid.UUID
    full_name: str
    username: str
    email: str
    phone: str | None
    status: str
    roles: list[RoleSummary]
    permissions: list[str]
    is_super_admin: bool


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")
    refresh_expires_in: int = Field(description="Refresh token lifetime in seconds")


class LoginResponse(TokenPair):
    user: CurrentUser
