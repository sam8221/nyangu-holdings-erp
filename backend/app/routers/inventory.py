"""Warehouses, stock levels, movements, adjustments and transfers."""

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from app.auth.dependencies import DbSession, auth_with
from app.auth.permissions import Perm
from app.routers.crud import crud_router
from app.schemas.common import ApiResponse, Page, PageParams, error_responses, ok, page_params
from app.schemas.inventory import (
    AdjustmentCreate,
    LowStockItem,
    MovementOut,
    MovementTypeLiteral,
    ProductStockOut,
    StockLevelOut,
    StockOperationResult,
    TransferCreate,
    WarehouseCreate,
    WarehouseOut,
    WarehouseUpdate,
)
from app.services.inventory_service import InventoryService, WarehouseService


def warehouse_filters(
    is_active: bool | None = None, branch_id: uuid.UUID | None = None
) -> dict[str, Any]:
    return {"is_active": is_active, "branch_id": branch_id}


warehouses_router = crud_router(
    prefix="/warehouses",
    tag="Inventory",
    service=WarehouseService,
    out=WarehouseOut,
    create=WarehouseCreate,
    update=WarehouseUpdate,
    view_perm=None,  # any signed-in user: sales and purchasing forms need the list
    create_perm=Perm.COMPANY_UPDATE,
    update_perm=Perm.COMPANY_UPDATE,
    delete_perm=Perm.COMPANY_UPDATE,
    filters=warehouse_filters,
)

inventory_router = APIRouter(prefix="/inventory", tags=["Inventory"])
Params = Annotated[PageParams, Depends(page_params)]
Viewer = auth_with(Perm.INVENTORY_VIEW)
_E = (401, 403, 422)


@inventory_router.get(
    "/stock-levels",
    summary="Stock on hand per product and warehouse",
    description="Zero rows are hidden unless include_zero=true. Sort: sku, name, quantity, "
    "updated_at.",
    response_model=ApiResponse[Page[StockLevelOut]],
    responses=error_responses(400, *_E),
)
def stock_levels(
    ctx: Viewer,
    db: DbSession,
    params: Params,
    warehouse_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    include_zero: bool = False,
) -> dict:
    data = InventoryService(db).stock_levels(
        params,
        warehouse_id=warehouse_id,
        product_id=product_id,
        category_id=category_id,
        include_zero=include_zero,
    )
    return ok(data, "Stock levels retrieved")


@inventory_router.get(
    "/products/{product_id}",
    summary="Stock of one product across warehouses",
    response_model=ApiResponse[ProductStockOut],
    responses=error_responses(404, *_E),
)
def product_stock(product_id: uuid.UUID, ctx: Viewer, db: DbSession) -> dict:
    return ok(InventoryService(db).product_stock(product_id), "Product stock retrieved")


@inventory_router.get(
    "/low-stock",
    summary="Products at or below their reorder level",
    response_model=ApiResponse[Page[LowStockItem]],
    responses=error_responses(*_E),
)
def low_stock(ctx: Viewer, db: DbSession, params: Params) -> dict:
    return ok(InventoryService(db).low_stock(params), "Low stock retrieved")


@inventory_router.get(
    "/movements",
    summary="Stock movement ledger",
    description="Sort: created_at, quantity.",
    response_model=ApiResponse[Page[MovementOut]],
    responses=error_responses(400, *_E),
)
def movements(
    ctx: Viewer,
    db: DbSession,
    params: Params,
    product_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    movement_type: MovementTypeLiteral | None = None,
    reference_number: Annotated[str | None, Query(max_length=30)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    data = InventoryService(db).movements(
        params,
        product_id=product_id,
        warehouse_id=warehouse_id,
        movement_type=movement_type,
        reference_number=reference_number,
        date_from=date_from,
        date_to=date_to,
    )
    return ok(data, "Stock movements retrieved")


@inventory_router.post(
    "/adjustments",
    summary="Adjust stock (count or write-off)",
    description="Each line gives either a signed quantity_change or a counted_quantity.",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[StockOperationResult],
    responses=error_responses(400, *_E),
)
def adjust_stock(
    body: AdjustmentCreate, ctx: auth_with(Perm.INVENTORY_ADJUST), db: DbSession
) -> dict:
    return ok(InventoryService(db).adjust(ctx, body), "Stock adjusted")


@inventory_router.post(
    "/transfers",
    summary="Transfer stock between warehouses",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[StockOperationResult],
    responses=error_responses(400, *_E),
)
def transfer_stock(
    body: TransferCreate, ctx: auth_with(Perm.INVENTORY_TRANSFER), db: DbSession
) -> dict:
    return ok(InventoryService(db).transfer(ctx, body), "Stock transferred")
