"""Finance: expenses, supplier bills and payments, receivables, payables and statements."""

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from app.auth.dependencies import DbSession, auth_with
from app.auth.permissions import Perm
from app.routers.crud import crud_router
from app.schemas.common import ApiResponse, Page, PageParams, error_responses, ok, page_params
from app.schemas.finance import (
    AgingReport,
    BillCreate,
    BillOut,
    BillStatusLiteral,
    BillSummary,
    CustomerStatement,
    ExpenseCategoryCreate,
    ExpenseCategoryOut,
    ExpenseCategoryUpdate,
    ExpenseCreate,
    ExpenseOut,
    ExpenseStatusLiteral,
    ExpenseUpdate,
    RejectComment,
    ReviewComment,
    SupplierPaymentCreate,
    SupplierPaymentOut,
)
from app.schemas.sales import CancelRequest
from app.services.finance_service import ExpenseCategoryService, FinanceService
from app.utils.time import local_today


def _active(is_active: bool | None = None) -> dict[str, Any]:
    return {"is_active": is_active}


expense_categories_router = crud_router(
    prefix="/finance/expense-categories",
    tag="Finance",
    service=ExpenseCategoryService,
    out=ExpenseCategoryOut,
    create=ExpenseCategoryCreate,
    update=ExpenseCategoryUpdate,
    view_perm=Perm.FINANCE_VIEW,
    create_perm=Perm.FINANCE_CREATE,
    update_perm=Perm.FINANCE_UPDATE,
    delete_perm=Perm.FINANCE_UPDATE,
    filters=_active,
)

router = APIRouter(prefix="/finance", tags=["Finance"])
Params = Annotated[PageParams, Depends(page_params)]
Viewer = auth_with(Perm.FINANCE_VIEW)
_E = (401, 403, 422)


# ---------------------------------------------------------------------- expenses
@router.get(
    "/expenses",
    summary="List expenses",
    description="Sort: expense_date, amount, expense_number, created_at.",
    response_model=ApiResponse[Page[ExpenseOut]],
    responses=error_responses(400, *_E),
)
def list_expenses(
    ctx: Viewer,
    db: DbSession,
    params: Params,
    status_: Annotated[ExpenseStatusLiteral | None, Query(alias="status")] = None,
    category_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    data = FinanceService(db).list_expenses(
        params,
        status=status_,
        category_id=category_id,
        branch_id=branch_id,
        date_from=date_from,
        date_to=date_to,
    )
    return ok(data, "Expenses retrieved")


@router.post(
    "/expenses",
    summary="Submit an expense for approval",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[ExpenseOut],
    responses=error_responses(400, *_E),
)
def create_expense(body: ExpenseCreate, ctx: auth_with(Perm.FINANCE_CREATE), db: DbSession) -> dict:
    return ok(FinanceService(db).create_expense(ctx, body), "Expense submitted")


@router.get(
    "/expenses/{expense_id}",
    summary="Get an expense",
    response_model=ApiResponse[ExpenseOut],
    responses=error_responses(404, *_E),
)
def get_expense(expense_id: uuid.UUID, ctx: Viewer, db: DbSession) -> dict:
    return ok(FinanceService(db).get_expense(expense_id), "Expense retrieved")


@router.put(
    "/expenses/{expense_id}",
    summary="Update a pending expense",
    response_model=ApiResponse[ExpenseOut],
    responses=error_responses(400, 404, *_E),
)
def update_expense(
    expense_id: uuid.UUID, body: ExpenseUpdate, ctx: auth_with(Perm.FINANCE_UPDATE), db: DbSession
) -> dict:
    return ok(FinanceService(db).update_expense(ctx, expense_id, body), "Expense updated")


@router.delete(
    "/expenses/{expense_id}",
    summary="Delete a pending expense",
    response_model=ApiResponse[None],
    responses=error_responses(404, *_E),
)
def delete_expense(
    expense_id: uuid.UUID, ctx: auth_with(Perm.FINANCE_UPDATE), db: DbSession
) -> dict:
    FinanceService(db).delete_expense(ctx, expense_id)
    return ok(None, "Expense deleted")


@router.post(
    "/expenses/{expense_id}/approve",
    summary="Approve an expense (not your own)",
    response_model=ApiResponse[ExpenseOut],
    responses=error_responses(404, *_E),
)
def approve_expense(
    expense_id: uuid.UUID,
    ctx: auth_with(Perm.FINANCE_APPROVE),
    db: DbSession,
    body: ReviewComment | None = None,
) -> dict:
    comment = body.comment if body else None
    return ok(FinanceService(db).review_expense(ctx, expense_id, True, comment), "Expense approved")


@router.post(
    "/expenses/{expense_id}/reject",
    summary="Reject an expense (not your own)",
    response_model=ApiResponse[ExpenseOut],
    responses=error_responses(404, *_E),
)
def reject_expense(
    expense_id: uuid.UUID,
    body: RejectComment,
    ctx: auth_with(Perm.FINANCE_APPROVE),
    db: DbSession,
) -> dict:
    data = FinanceService(db).review_expense(ctx, expense_id, False, body.comment)
    return ok(data, "Expense rejected")


# ---------------------------------------------------------------------- supplier bills
@router.get(
    "/bills",
    summary="List supplier bills",
    description="Sort: bill_date, due_date, total, bill_number, created_at.",
    response_model=ApiResponse[Page[BillSummary]],
    responses=error_responses(400, *_E),
)
def list_bills(
    ctx: Viewer,
    db: DbSession,
    params: Params,
    status_: Annotated[BillStatusLiteral | None, Query(alias="status")] = None,
    supplier_id: uuid.UUID | None = None,
    overdue: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    data = FinanceService(db).list_bills(
        params,
        status=status_,
        supplier_id=supplier_id,
        overdue=overdue,
        date_from=date_from,
        date_to=date_to,
    )
    return ok(data, "Supplier bills retrieved")


@router.post(
    "/bills",
    summary="Enter a supplier bill",
    description="Optionally linked to a purchase order; total billed cannot exceed the order.",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[BillOut],
    responses=error_responses(400, 409, *_E),
)
def create_bill(body: BillCreate, ctx: auth_with(Perm.FINANCE_CREATE), db: DbSession) -> dict:
    return ok(FinanceService(db).create_bill(ctx, body), "Supplier bill entered")


@router.get(
    "/bills/{bill_id}",
    summary="Get a supplier bill with payments",
    response_model=ApiResponse[BillOut],
    responses=error_responses(404, *_E),
)
def get_bill(bill_id: uuid.UUID, ctx: Viewer, db: DbSession) -> dict:
    return ok(FinanceService(db).get_bill(bill_id), "Supplier bill retrieved")


@router.post(
    "/bills/{bill_id}/approve",
    summary="Approve a supplier bill for payment",
    response_model=ApiResponse[BillOut],
    responses=error_responses(404, *_E),
)
def approve_bill(bill_id: uuid.UUID, ctx: auth_with(Perm.FINANCE_APPROVE), db: DbSession) -> dict:
    return ok(FinanceService(db).approve_bill(ctx, bill_id), "Supplier bill approved")


@router.post(
    "/bills/{bill_id}/cancel",
    summary="Cancel an unpaid supplier bill",
    response_model=ApiResponse[BillOut],
    responses=error_responses(404, *_E),
)
def cancel_bill(
    bill_id: uuid.UUID, body: CancelRequest, ctx: auth_with(Perm.FINANCE_APPROVE), db: DbSession
) -> dict:
    return ok(FinanceService(db).cancel_bill(ctx, bill_id, body.reason), "Supplier bill cancelled")


@router.post(
    "/bills/{bill_id}/payments",
    summary="Pay a supplier bill",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[SupplierPaymentOut],
    responses=error_responses(404, *_E),
)
def pay_bill(
    bill_id: uuid.UUID,
    body: SupplierPaymentCreate,
    ctx: auth_with(Perm.FINANCE_CREATE),
    db: DbSession,
) -> dict:
    return ok(FinanceService(db).pay_bill(ctx, bill_id, body), "Supplier payment recorded")


@router.get(
    "/supplier-payments",
    summary="List supplier payments",
    description="Sort: payment_date, amount, payment_number.",
    response_model=ApiResponse[Page[SupplierPaymentOut]],
    responses=error_responses(400, *_E),
)
def list_supplier_payments(
    ctx: Viewer,
    db: DbSession,
    params: Params,
    supplier_id: uuid.UUID | None = None,
    bill_id: uuid.UUID | None = None,
    status_: Annotated[str | None, Query(alias="status", pattern="^(POSTED|VOIDED)$")] = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    data = FinanceService(db).list_supplier_payments(
        params,
        supplier_id=supplier_id,
        bill_id=bill_id,
        status=status_,
        date_from=date_from,
        date_to=date_to,
    )
    return ok(data, "Supplier payments retrieved")


@router.post(
    "/supplier-payments/{payment_id}/void",
    summary="Void a supplier payment",
    response_model=ApiResponse[SupplierPaymentOut],
    responses=error_responses(404, *_E),
)
def void_supplier_payment(
    payment_id: uuid.UUID,
    body: CancelRequest,
    ctx: auth_with(Perm.FINANCE_APPROVE),
    db: DbSession,
) -> dict:
    data = FinanceService(db).void_supplier_payment(ctx, payment_id, body.reason)
    return ok(data, "Supplier payment voided")


# ---------------------------------------------------------------------- receivables / payables
@router.get(
    "/receivables",
    summary="Accounts receivable aging by customer",
    description="Outstanding invoice balances bucketed by days past due, as of today.",
    response_model=ApiResponse[AgingReport],
    responses=error_responses(*_E),
)
def receivables(ctx: Viewer, db: DbSession) -> dict:
    return ok(FinanceService(db).receivables_aging(), "Receivables aging")


@router.get(
    "/payables",
    summary="Accounts payable aging by supplier",
    description="Outstanding approved bill balances bucketed by days past due, as of today.",
    response_model=ApiResponse[AgingReport],
    responses=error_responses(*_E),
)
def payables(ctx: Viewer, db: DbSession) -> dict:
    return ok(FinanceService(db).payables_aging(), "Payables aging")


@router.get(
    "/customers/{customer_id}/statement",
    summary="Customer account statement",
    description="Invoices (debits) and payments (credits) with a running balance. "
    "Defaults to the current month.",
    response_model=ApiResponse[CustomerStatement],
    responses=error_responses(404, *_E),
)
def customer_statement(
    customer_id: uuid.UUID,
    ctx: Viewer,
    db: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    today = local_today()
    start = date_from or today.replace(day=1)
    end = date_to or today
    return ok(FinanceService(db).customer_statement(customer_id, start, end), "Customer statement")
