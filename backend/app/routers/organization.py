"""Company profile, branches, departments and system settings."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.auth.dependencies import CurrentAuth, DbSession, auth_with
from app.auth.permissions import Perm
from app.schemas.common import ApiResponse, Page, PageParams, error_responses, ok, page_params
from app.schemas.organization import (
    BranchCreate,
    BranchOut,
    BranchUpdate,
    CompanyOut,
    CompanyUpdate,
    DepartmentCreate,
    DepartmentOut,
    DepartmentUpdate,
    SettingsOut,
    SettingsUpdate,
)
from app.services.organization_service import OrganizationService
from app.services.settings_service import SettingsService

company_router = APIRouter(prefix="/company", tags=["Company"])
branches_router = APIRouter(prefix="/branches", tags=["Branches"])
departments_router = APIRouter(prefix="/departments", tags=["Departments"])
settings_router = APIRouter(prefix="/settings", tags=["Settings"])

Params = Annotated[PageParams, Depends(page_params)]
_E = (401, 403, 422)


# ---------------------------------------------------------------------- company
@company_router.get(
    "",
    summary="Company profile",
    response_model=ApiResponse[CompanyOut],
    responses=error_responses(401, 403, 404),
)
def get_company(ctx: auth_with(Perm.COMPANY_VIEW), db: DbSession) -> dict:
    return ok(OrganizationService(db).company(), "Company profile")


@company_router.put(
    "",
    summary="Update the company profile",
    response_model=ApiResponse[CompanyOut],
    responses=error_responses(400, 404, *_E),
)
def update_company(body: CompanyUpdate, ctx: auth_with(Perm.COMPANY_UPDATE), db: DbSession) -> dict:
    return ok(OrganizationService(db).update_company(ctx, body), "Company profile updated")


# ---------------------------------------------------------------------- branches
@branches_router.get(
    "",
    summary="List branches",
    description="Any signed-in user can read branches (needed for forms). Sort: code, name, "
    "created_at.",
    response_model=ApiResponse[Page[BranchOut]],
    responses=error_responses(400, 401, 422),
)
def list_branches(
    ctx: CurrentAuth, db: DbSession, params: Params, is_active: bool | None = None
) -> dict:
    return ok(OrganizationService(db).list_branches(params, is_active), "Branches retrieved")


@branches_router.post(
    "",
    summary="Create a branch",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[BranchOut],
    responses=error_responses(409, *_E),
)
def create_branch(body: BranchCreate, ctx: auth_with(Perm.COMPANY_UPDATE), db: DbSession) -> dict:
    return ok(OrganizationService(db).create_branch(ctx, body), "Branch created successfully")


@branches_router.get(
    "/{branch_id}",
    summary="Get a branch",
    response_model=ApiResponse[BranchOut],
    responses=error_responses(401, 404, 422),
)
def get_branch(branch_id: uuid.UUID, ctx: CurrentAuth, db: DbSession) -> dict:
    return ok(OrganizationService(db).get_branch(branch_id), "Branch retrieved")


@branches_router.put(
    "/{branch_id}",
    summary="Update a branch",
    response_model=ApiResponse[BranchOut],
    responses=error_responses(400, 404, 409, *_E),
)
def update_branch(
    branch_id: uuid.UUID, body: BranchUpdate, ctx: auth_with(Perm.COMPANY_UPDATE), db: DbSession
) -> dict:
    return ok(OrganizationService(db).update_branch(ctx, branch_id, body), "Branch updated")


@branches_router.delete(
    "/{branch_id}",
    summary="Delete an unused branch",
    response_model=ApiResponse[None],
    responses=error_responses(404, *_E),
)
def delete_branch(branch_id: uuid.UUID, ctx: auth_with(Perm.COMPANY_UPDATE), db: DbSession) -> dict:
    OrganizationService(db).delete_branch(ctx, branch_id)
    return ok(None, "Branch deleted")


# ---------------------------------------------------------------------- departments
@departments_router.get(
    "",
    summary="List departments",
    description="Any signed-in user can read departments. Sort: code, name, created_at.",
    response_model=ApiResponse[Page[DepartmentOut]],
    responses=error_responses(400, 401, 422),
)
def list_departments(
    ctx: CurrentAuth, db: DbSession, params: Params, is_active: bool | None = None
) -> dict:
    data = OrganizationService(db).list_departments(params, is_active)
    return ok(data, "Departments retrieved")


@departments_router.post(
    "",
    summary="Create a department",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[DepartmentOut],
    responses=error_responses(409, *_E),
)
def create_department(
    body: DepartmentCreate, ctx: auth_with(Perm.COMPANY_UPDATE), db: DbSession
) -> dict:
    data = OrganizationService(db).create_department(ctx, body)
    return ok(data, "Department created successfully")


@departments_router.get(
    "/{department_id}",
    summary="Get a department",
    response_model=ApiResponse[DepartmentOut],
    responses=error_responses(401, 404, 422),
)
def get_department(department_id: uuid.UUID, ctx: CurrentAuth, db: DbSession) -> dict:
    return ok(OrganizationService(db).get_department(department_id), "Department retrieved")


@departments_router.put(
    "/{department_id}",
    summary="Update a department",
    response_model=ApiResponse[DepartmentOut],
    responses=error_responses(400, 404, 409, *_E),
)
def update_department(
    department_id: uuid.UUID,
    body: DepartmentUpdate,
    ctx: auth_with(Perm.COMPANY_UPDATE),
    db: DbSession,
) -> dict:
    data = OrganizationService(db).update_department(ctx, department_id, body)
    return ok(data, "Department updated")


@departments_router.delete(
    "/{department_id}",
    summary="Delete an unused department",
    response_model=ApiResponse[None],
    responses=error_responses(404, *_E),
)
def delete_department(
    department_id: uuid.UUID, ctx: auth_with(Perm.COMPANY_UPDATE), db: DbSession
) -> dict:
    OrganizationService(db).delete_department(ctx, department_id)
    return ok(None, "Department deleted")


# ---------------------------------------------------------------------- settings
@settings_router.get(
    "",
    summary="System settings",
    response_model=ApiResponse[SettingsOut],
    responses=error_responses(401, 403),
)
def get_settings_(ctx: auth_with(Perm.SETTINGS_VIEW), db: DbSession) -> dict:
    return ok(SettingsService(db).all(), "Settings retrieved")


@settings_router.put(
    "",
    summary="Update system settings",
    description="Only the fields sent are changed.",
    response_model=ApiResponse[SettingsOut],
    responses=error_responses(*_E),
)
def update_settings(
    body: SettingsUpdate, ctx: auth_with(Perm.SETTINGS_UPDATE), db: DbSession
) -> dict:
    return ok(SettingsService(db).update(ctx, body), "Settings updated")
