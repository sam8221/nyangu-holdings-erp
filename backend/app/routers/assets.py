"""Fixed assets."""

import uuid
from typing import Any, Literal

from fastapi import APIRouter

from app.auth.dependencies import DbSession, auth_with
from app.auth.permissions import Perm
from app.routers.crud import crud_router
from app.schemas.assets import (
    AssetAssign,
    AssetCategoryCreate,
    AssetCategoryOut,
    AssetCategoryUpdate,
    AssetCreate,
    AssetDispose,
    AssetOut,
    AssetUpdate,
    DepreciationSchedule,
)
from app.schemas.common import ApiResponse, error_responses, ok
from app.services.assets_service import AssetCategoryService, AssetService


def category_filters(is_active: bool | None = None) -> dict[str, Any]:
    return {"is_active": is_active}


def asset_filters(
    status: Literal["IN_USE", "IN_STORE", "UNDER_MAINTENANCE", "DISPOSED"] | None = None,
    category_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    assigned_employee_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "category_id": category_id,
        "branch_id": branch_id,
        "assigned_employee_id": assigned_employee_id,
    }


asset_categories_router = crud_router(
    prefix="/asset-categories",
    tag="Assets",
    service=AssetCategoryService,
    out=AssetCategoryOut,
    create=AssetCategoryCreate,
    update=AssetCategoryUpdate,
    view_perm=Perm.ASSETS_VIEW,
    create_perm=Perm.ASSETS_CREATE,
    update_perm=Perm.ASSETS_UPDATE,
    delete_perm=Perm.ASSETS_DELETE,
    filters=category_filters,
)

assets_router = crud_router(
    prefix="/assets",
    tag="Assets",
    service=AssetService,
    out=AssetOut,
    create=AssetCreate,
    update=AssetUpdate,
    view_perm=Perm.ASSETS_VIEW,
    create_perm=Perm.ASSETS_CREATE,
    update_perm=Perm.ASSETS_UPDATE,
    delete_perm=Perm.ASSETS_DELETE,
    filters=asset_filters,
)

asset_actions_router = APIRouter(prefix="/assets", tags=["Assets"])
_E = (401, 403, 404, 422)


@asset_actions_router.post(
    "/{asset_id}/assign",
    summary="Assign an asset to an employee, or return it to store",
    response_model=ApiResponse[AssetOut],
    responses=error_responses(*_E),
)
def assign_asset(
    asset_id: uuid.UUID, body: AssetAssign, ctx: auth_with(Perm.ASSETS_UPDATE), db: DbSession
) -> dict:
    return ok(AssetService(db).assign(ctx, asset_id, body), "Asset assignment updated")


@asset_actions_router.post(
    "/{asset_id}/dispose",
    summary="Dispose of an asset (sale or write-off)",
    description="Records proceeds and the gain or loss against book value.",
    response_model=ApiResponse[AssetOut],
    responses=error_responses(*_E),
)
def dispose_asset(
    asset_id: uuid.UUID, body: AssetDispose, ctx: auth_with(Perm.ASSETS_DELETE), db: DbSession
) -> dict:
    return ok(AssetService(db).dispose(ctx, asset_id, body), "Asset disposed")


@asset_actions_router.get(
    "/{asset_id}/depreciation-schedule",
    summary="Yearly depreciation schedule",
    response_model=ApiResponse[DepreciationSchedule],
    responses=error_responses(*_E),
)
def depreciation_schedule(
    asset_id: uuid.UUID, ctx: auth_with(Perm.ASSETS_VIEW), db: DbSession
) -> dict:
    return ok(AssetService(db).schedule(asset_id), "Depreciation schedule")
