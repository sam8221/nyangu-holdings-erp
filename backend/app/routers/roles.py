"""Role and permission endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.auth.dependencies import AuthContext, DbSession, require_permissions
from app.auth.permissions import Perm
from app.schemas.common import ApiResponse, error_responses, ok
from app.schemas.rbac import PermissionOut, RoleCreate, RoleOut, RoleUpdate
from app.services.role_service import RoleService

roles_router = APIRouter(prefix="/roles", tags=["Roles"])
permissions_router = APIRouter(prefix="/permissions", tags=["Permissions"])

_COMMON_ERRORS = (401, 403, 422)


def _auth(*perms: Perm) -> type[AuthContext]:
    return Annotated[AuthContext, Depends(require_permissions(*perms))]  # type: ignore[return-value]


@roles_router.get(
    "",
    summary="List roles with permissions and user counts",
    response_model=ApiResponse[list[RoleOut]],
    responses=error_responses(*_COMMON_ERRORS),
)
def list_roles(
    ctx: _auth(Perm.ROLES_VIEW),
    db: DbSession,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> dict:
    return ok(RoleService(db).list(search), "Roles retrieved")


@roles_router.post(
    "",
    summary="Create a custom role",
    description="You can only grant permissions you hold yourself.",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[RoleOut],
    responses=error_responses(400, 409, *_COMMON_ERRORS),
)
def create_role(body: RoleCreate, ctx: _auth(Perm.ROLES_CREATE), db: DbSession) -> dict:
    return ok(RoleService(db).create(ctx, body), "Role created successfully")


@roles_router.get(
    "/{role_id}",
    summary="Get a role",
    response_model=ApiResponse[RoleOut],
    responses=error_responses(404, *_COMMON_ERRORS),
)
def get_role(role_id: uuid.UUID, ctx: _auth(Perm.ROLES_VIEW), db: DbSession) -> dict:
    return ok(RoleService(db).get(role_id), "Role retrieved")


@roles_router.put(
    "/{role_id}",
    summary="Update a role",
    description="Only fields sent are changed. `permissions` replaces the role's whole set.",
    response_model=ApiResponse[RoleOut],
    responses=error_responses(400, 404, 409, *_COMMON_ERRORS),
)
def update_role(
    role_id: uuid.UUID, body: RoleUpdate, ctx: _auth(Perm.ROLES_UPDATE), db: DbSession
) -> dict:
    return ok(RoleService(db).update(ctx, role_id, body), "Role updated successfully")


@roles_router.delete(
    "/{role_id}",
    summary="Delete an unused custom role",
    response_model=ApiResponse[None],
    responses=error_responses(404, *_COMMON_ERRORS),
)
def delete_role(role_id: uuid.UUID, ctx: _auth(Perm.ROLES_DELETE), db: DbSession) -> dict:
    RoleService(db).delete(ctx, role_id)
    return ok(None, "Role deleted successfully")


@permissions_router.get(
    "",
    summary="Permission catalogue",
    response_model=ApiResponse[list[PermissionOut]],
    responses=error_responses(*_COMMON_ERRORS),
)
def list_permissions(
    ctx: _auth(Perm.PERMISSIONS_VIEW),
    db: DbSession,
    module: Annotated[
        str | None, Query(max_length=50, description="Filter by module, e.g. users")
    ] = None,
) -> dict:
    perms = RoleService(db).list_permissions(module)
    return ok([PermissionOut.model_validate(p) for p in perms], "Permissions retrieved")
