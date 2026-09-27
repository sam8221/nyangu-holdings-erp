"""Purchase orders and goods received notes."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.auth.dependencies import DbSession, auth_with, auth_with_any
from app.auth.permissions import Perm
from app.schemas.common import ApiResponse, Page, PageParams, error_responses, ok, page_params
from app.schemas.procurement import (
    GRNCreate,
    GRNOut,
    POCreate,
    POOut,
    POStatusLiteral,
    POSummary,
    POUpdate,
)
from app.schemas.sales import CancelRequest
from app.services.procurement_service import ProcurementService

router = APIRouter(prefix="/procurement", tags=["Procurement"])
Params = Annotated[PageParams, Depends(page_params)]
_E = (401, 403, 422)


@router.get(
    "/purchase-orders",
    summary="List purchase orders",
    description="Sort: po_number, order_date, expected_date, total, created_at.",
    response_model=ApiResponse[Page[POSummary]],
    responses=error_responses(400, *_E),
)
def list_orders(
    ctx: auth_with(Perm.PROCUREMENT_VIEW),
    db: DbSession,
    params: Params,
    status_: Annotated[POStatusLiteral | None, Query(alias="status")] = None,
    supplier_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    data = ProcurementService(db).list_orders(
        params, status=status_, supplier_id=supplier_id, date_from=date_from, date_to=date_to
    )
    return ok(data, "Purchase orders retrieved")


@router.post(
    "/purchase-orders",
    summary="Create a draft purchase order",
    description="Costs and VAT default from the product. Approvers are notified.",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[POOut],
    responses=error_responses(400, *_E),
)
def create_order(body: POCreate, ctx: auth_with(Perm.PROCUREMENT_CREATE), db: DbSession) -> dict:
    return ok(ProcurementService(db).create_order(ctx, body), "Purchase order created")


@router.get(
    "/purchase-orders/{order_id}",
    summary="Get a purchase order with lines and receipts",
    response_model=ApiResponse[POOut],
    responses=error_responses(404, *_E),
)
def get_order(order_id: uuid.UUID, ctx: auth_with(Perm.PROCUREMENT_VIEW), db: DbSession) -> dict:
    return ok(ProcurementService(db).get_order(order_id), "Purchase order retrieved")


@router.put(
    "/purchase-orders/{order_id}",
    summary="Update a draft purchase order",
    response_model=ApiResponse[POOut],
    responses=error_responses(400, 404, *_E),
)
def update_order(
    order_id: uuid.UUID, body: POUpdate, ctx: auth_with(Perm.PROCUREMENT_UPDATE), db: DbSession
) -> dict:
    return ok(ProcurementService(db).update_order(ctx, order_id, body), "Purchase order updated")


@router.delete(
    "/purchase-orders/{order_id}",
    summary="Delete a draft purchase order",
    response_model=ApiResponse[None],
    responses=error_responses(404, *_E),
)
def delete_order(
    order_id: uuid.UUID, ctx: auth_with(Perm.PROCUREMENT_DELETE), db: DbSession
) -> dict:
    ProcurementService(db).delete_order(ctx, order_id)
    return ok(None, "Purchase order deleted")


@router.post(
    "/purchase-orders/{order_id}/approve",
    summary="Approve a draft purchase order",
    response_model=ApiResponse[POOut],
    responses=error_responses(404, *_E),
)
def approve_order(
    order_id: uuid.UUID, ctx: auth_with(Perm.PROCUREMENT_APPROVE), db: DbSession
) -> dict:
    return ok(ProcurementService(db).approve_order(ctx, order_id), "Purchase order approved")


@router.post(
    "/purchase-orders/{order_id}/cancel",
    summary="Cancel an order with nothing received",
    response_model=ApiResponse[POOut],
    responses=error_responses(404, *_E),
)
def cancel_order(
    order_id: uuid.UUID,
    body: CancelRequest,
    ctx: auth_with(Perm.PROCUREMENT_DELETE),
    db: DbSession,
) -> dict:
    data = ProcurementService(db).cancel_order(ctx, order_id, body.reason)
    return ok(data, "Purchase order cancelled")


@router.post(
    "/purchase-orders/{order_id}/close",
    summary="Close a partly received order (accept the short delivery)",
    response_model=ApiResponse[POOut],
    responses=error_responses(404, *_E),
)
def close_order(
    order_id: uuid.UUID,
    body: CancelRequest,
    ctx: auth_with(Perm.PROCUREMENT_UPDATE),
    db: DbSession,
) -> dict:
    return ok(
        ProcurementService(db).close_order(ctx, order_id, body.reason), "Purchase order closed"
    )


@router.get(
    "/goods-receipts",
    summary="List goods received notes",
    description="Sort: received_date, grn_number.",
    response_model=ApiResponse[Page[GRNOut]],
    responses=error_responses(400, *_E),
)
def list_receipts(
    ctx: auth_with_any(Perm.PROCUREMENT_VIEW, Perm.INVENTORY_VIEW),
    db: DbSession,
    params: Params,
    purchase_order_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    data = ProcurementService(db).list_receipts(
        params, purchase_order_id=purchase_order_id, date_from=date_from, date_to=date_to
    )
    return ok(data, "Goods receipts retrieved")


@router.post(
    "/goods-receipts",
    summary="Receive goods against an approved purchase order",
    description="Adds stock to the warehouse and updates each product's average cost. "
    "Partial deliveries are allowed.",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[GRNOut],
    responses=error_responses(400, 404, *_E),
)
def receive_goods(
    body: GRNCreate,
    ctx: auth_with_any(Perm.PROCUREMENT_UPDATE, Perm.INVENTORY_ADJUST),
    db: DbSession,
) -> dict:
    return ok(ProcurementService(db).receive(ctx, body), "Goods received")


@router.get(
    "/goods-receipts/{receipt_id}",
    summary="Get a goods received note",
    response_model=ApiResponse[GRNOut],
    responses=error_responses(404, *_E),
)
def get_receipt(
    receipt_id: uuid.UUID,
    ctx: auth_with_any(Perm.PROCUREMENT_VIEW, Perm.INVENTORY_VIEW),
    db: DbSession,
) -> dict:
    return ok(ProcurementService(db).get_receipt(receipt_id), "Goods receipt retrieved")
