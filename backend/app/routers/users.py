"""User management endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status

from app.auth.dependencies import AuthContext, DbSession, require_permissions
from app.auth.permissions import Perm
from app.schemas.common import ApiResponse, Page, PageParams, error_responses, ok, page_params
from app.schemas.user import (
    AdminPasswordReset,
    UserCreate,
    UserDetail,
    UserOut,
    UserRolesUpdate,
    UserStatusUpdate,
    UserUpdate,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])

_COMMON_ERRORS = (401, 403, 422)


def _auth(*perms: Perm) -> type[AuthContext]:
    return Annotated[AuthContext, Depends(require_permissions(*perms))]  # type: ignore[return-value]


@router.get(
    "",
    summary="List users",
    description="Sortable by: full_name, username, email, status, created_at, last_login_at.",
    response_model=ApiResponse[Page[UserOut]],
    responses=error_responses(400, *_COMMON_ERRORS),
)
def list_users(
    ctx: _auth(Perm.USERS_VIEW),
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    status_: Annotated[
        Literal["ACTIVE", "INACTIVE"] | None, Query(alias="status", description="Filter by status")
    ] = None,
    role: Annotated[
        str | None, Query(max_length=50, description="Filter by role name, e.g. ACCOUNTANT")
    ] = None,
) -> dict:
    return ok(UserService(db).list(params, status=status_, role=role), "Users retrieved")


@router.post(
    "",
    summary="Create a user",
    description="Setting role_ids also requires users.assign_roles.",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[UserDetail],
    responses=error_responses(400, 409, *_COMMON_ERRORS),
)
def create_user(body: UserCreate, ctx: _auth(Perm.USERS_CREATE), db: DbSession) -> dict:
    return ok(UserService(db).create(ctx, body), "User created successfully")


@router.get(
    "/{user_id}",
    summary="Get a user",
    response_model=ApiResponse[UserDetail],
    responses=error_responses(404, *_COMMON_ERRORS),
)
def get_user(user_id: uuid.UUID, ctx: _auth(Perm.USERS_VIEW), db: DbSession) -> dict:
    return ok(UserService(db).get(user_id), "User retrieved")


@router.put(
    "/{user_id}",
    summary="Update a user's profile",
    response_model=ApiResponse[UserDetail],
    responses=error_responses(400, 404, 409, *_COMMON_ERRORS),
)
def update_user(
    user_id: uuid.UUID, body: UserUpdate, ctx: _auth(Perm.USERS_UPDATE), db: DbSession
) -> dict:
    return ok(UserService(db).update(ctx, user_id, body), "User updated successfully")


@router.patch(
    "/{user_id}/status",
    summary="Activate or deactivate a user",
    description="Deactivating ends every session of that user immediately.",
    response_model=ApiResponse[UserDetail],
    responses=error_responses(404, *_COMMON_ERRORS),
)
def set_user_status(
    user_id: uuid.UUID, body: UserStatusUpdate, ctx: _auth(Perm.USERS_UPDATE), db: DbSession
) -> dict:
    data = UserService(db).set_status(ctx, user_id, body.status)
    verb = "activated" if body.status == "ACTIVE" else "deactivated"
    return ok(data, f"User {verb} successfully")


@router.put(
    "/{user_id}/roles",
    summary="Replace a user's roles",
    response_model=ApiResponse[UserDetail],
    responses=error_responses(400, 404, *_COMMON_ERRORS),
)
def set_user_roles(
    user_id: uuid.UUID,
    body: UserRolesUpdate,
    ctx: _auth(Perm.USERS_ASSIGN_ROLES),
    db: DbSession,
) -> dict:
    return ok(UserService(db).set_roles(ctx, user_id, body.role_ids), "User roles updated")


@router.post(
    "/{user_id}/reset-password",
    summary="Reset a user's password (admin)",
    description="Ends every session of that user.",
    response_model=ApiResponse[None],
    responses=error_responses(404, *_COMMON_ERRORS),
)
def reset_user_password(
    user_id: uuid.UUID,
    body: AdminPasswordReset,
    ctx: _auth(Perm.USERS_RESET_PASSWORD),
    db: DbSession,
) -> dict:
    UserService(db).reset_password(ctx, user_id, body.new_password)
    return ok(None, "Password reset successfully")
