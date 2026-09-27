"""Sales invoices, customer payments and invoice PDFs."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select

from app.auth.dependencies import DbSession, auth_with, auth_with_any
from app.auth.permissions import Perm
from app.models.organization import Company
from app.schemas.common import ApiResponse, Page, PageParams, error_responses, ok, page_params
from app.schemas.sales import (
    CancelRequest,
    InvoiceCreate,
    InvoiceOut,
    InvoiceStatusLiteral,
    InvoiceSummary,
    InvoiceUpdate,
    PaymentCreate,
    PaymentMethod,
    PaymentOut,
)
from app.services.documents import render_invoice_pdf
from app.services.sales_service import SalesService
from app.services.settings_service import SettingsService

router = APIRouter(prefix="/sales", tags=["Sales"])
Params = Annotated[PageParams, Depends(page_params)]
_E = (401, 403, 422)


# ---------------------------------------------------------------------- invoices
@router.get(
    "/invoices",
    summary="List sales invoices",
    description="Sort: invoice_date, due_date, invoice_number, total, created_at.",
    response_model=ApiResponse[Page[InvoiceSummary]],
    responses=error_responses(400, *_E),
)
def list_invoices(
    ctx: auth_with(Perm.SALES_VIEW),
    db: DbSession,
    params: Params,
    status_: Annotated[InvoiceStatusLiteral | None, Query(alias="status")] = None,
    customer_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    overdue: bool | None = None,
) -> dict:
    data = SalesService(db).list_invoices(
        params,
        status=status_,
        customer_id=customer_id,
        date_from=date_from,
        date_to=date_to,
        overdue=overdue,
    )
    return ok(data, "Invoices retrieved")


@router.post(
    "/invoices",
    summary="Create a draft invoice",
    description="Prices and VAT default from the product; the due date from the customer's "
    "payment terms. Drafts do not affect stock.",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[InvoiceOut],
    responses=error_responses(400, *_E),
)
def create_invoice(body: InvoiceCreate, ctx: auth_with(Perm.SALES_CREATE), db: DbSession) -> dict:
    return ok(SalesService(db).create_invoice(ctx, body), "Draft invoice created")


@router.get(
    "/invoices/{invoice_id}",
    summary="Get an invoice with lines and payments",
    response_model=ApiResponse[InvoiceOut],
    responses=error_responses(404, *_E),
)
def get_invoice(invoice_id: uuid.UUID, ctx: auth_with(Perm.SALES_VIEW), db: DbSession) -> dict:
    return ok(SalesService(db).get_invoice(invoice_id), "Invoice retrieved")


@router.put(
    "/invoices/{invoice_id}",
    summary="Update a draft invoice",
    response_model=ApiResponse[InvoiceOut],
    responses=error_responses(400, 404, *_E),
)
def update_invoice(
    invoice_id: uuid.UUID, body: InvoiceUpdate, ctx: auth_with(Perm.SALES_UPDATE), db: DbSession
) -> dict:
    return ok(SalesService(db).update_invoice(ctx, invoice_id, body), "Draft invoice updated")


@router.delete(
    "/invoices/{invoice_id}",
    summary="Delete a draft invoice",
    response_model=ApiResponse[None],
    responses=error_responses(404, *_E),
)
def delete_invoice(invoice_id: uuid.UUID, ctx: auth_with(Perm.SALES_DELETE), db: DbSession) -> dict:
    SalesService(db).delete_draft(ctx, invoice_id)
    return ok(None, "Draft invoice deleted")


@router.post(
    "/invoices/{invoice_id}/approve",
    summary="Approve and issue a draft invoice",
    description="Assigns the invoice number, checks the customer's credit limit and issues "
    "goods from the warehouse.",
    response_model=ApiResponse[InvoiceOut],
    responses=error_responses(404, *_E),
)
def approve_invoice(
    invoice_id: uuid.UUID, ctx: auth_with(Perm.SALES_APPROVE), db: DbSession
) -> dict:
    return ok(SalesService(db).approve_invoice(ctx, invoice_id), "Invoice issued")


@router.post(
    "/invoices/{invoice_id}/cancel",
    summary="Cancel an issued invoice",
    description="Only invoices without payments. Goods are returned to stock.",
    response_model=ApiResponse[InvoiceOut],
    responses=error_responses(404, *_E),
)
def cancel_invoice(
    invoice_id: uuid.UUID,
    body: CancelRequest,
    ctx: auth_with(Perm.SALES_DELETE),
    db: DbSession,
) -> dict:
    return ok(SalesService(db).cancel_invoice(ctx, invoice_id, body.reason), "Invoice cancelled")


@router.get(
    "/invoices/{invoice_id}/pdf",
    summary="Download the invoice as a PDF",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "PDF document"},
        **error_responses(404, *_E),
    },
)
def invoice_pdf(invoice_id: uuid.UUID, ctx: auth_with(Perm.SALES_VIEW), db: DbSession) -> Response:
    invoice = SalesService(db).get_invoice(invoice_id)
    company = db.scalars(select(Company).limit(1)).first()
    footer = SettingsService(db).get("invoice_footer")
    pdf = render_invoice_pdf(invoice, company, footer)
    filename = f"{invoice.invoice_number or 'draft-' + str(invoice.id)[:8]}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------- payments
@router.post(
    "/invoices/{invoice_id}/payments",
    summary="Record a customer payment against an invoice",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[PaymentOut],
    responses=error_responses(404, *_E),
)
def record_payment(
    invoice_id: uuid.UUID,
    body: PaymentCreate,
    ctx: auth_with(Perm.FINANCE_CREATE),
    db: DbSession,
) -> dict:
    return ok(SalesService(db).record_payment(ctx, invoice_id, body), "Payment recorded")


@router.get(
    "/payments",
    summary="List customer payments (receipts)",
    description="Sort: payment_date, amount, receipt_number.",
    response_model=ApiResponse[Page[PaymentOut]],
    responses=error_responses(400, *_E),
)
def list_payments(
    ctx: auth_with_any(Perm.SALES_VIEW, Perm.FINANCE_VIEW),
    db: DbSession,
    params: Params,
    customer_id: uuid.UUID | None = None,
    invoice_id: uuid.UUID | None = None,
    method: PaymentMethod | None = None,
    status_: Annotated[str | None, Query(alias="status", pattern="^(POSTED|VOIDED)$")] = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    data = SalesService(db).list_payments(
        params,
        customer_id=customer_id,
        invoice_id=invoice_id,
        method=method,
        status=status_,
        date_from=date_from,
        date_to=date_to,
    )
    return ok(data, "Payments retrieved")


@router.post(
    "/payments/{payment_id}/void",
    summary="Void a customer payment",
    description="Reopens the invoice balance.",
    response_model=ApiResponse[PaymentOut],
    responses=error_responses(404, *_E),
)
def void_payment(
    payment_id: uuid.UUID,
    body: CancelRequest,
    ctx: auth_with(Perm.FINANCE_APPROVE),
    db: DbSession,
) -> dict:
    return ok(SalesService(db).void_payment(ctx, payment_id, body.reason), "Payment voided")
