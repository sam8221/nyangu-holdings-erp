"""Quotations: list, create, edit, status, PDF and conversion to an invoice."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select

from app.auth.dependencies import DbSession, auth_with
from app.auth.permissions import Perm
from app.models.organization import Company
from app.schemas.common import ApiResponse, Page, PageParams, error_responses, ok, page_params
from app.schemas.sales import (
    ConvertQuotation,
    InvoiceOut,
    QuotationCreate,
    QuotationOut,
    QuotationStatusChange,
    QuotationStatusLiteral,
    QuotationSummary,
    QuotationUpdate,
)
from app.services.documents import render_quotation_pdf
from app.services.quotation_service import QuotationService
from app.services.settings_service import SettingsService

router = APIRouter(prefix="/sales/quotations", tags=["Sales"])
Params = Annotated[PageParams, Depends(page_params)]
_E = (401, 403, 422)


@router.get(
    "",
    summary="List quotations",
    description="Sort: quote_date, valid_until, quote_number, total, created_at.",
    response_model=ApiResponse[Page[QuotationSummary]],
    responses=error_responses(400, *_E),
)
def list_quotations(
    ctx: auth_with(Perm.SALES_VIEW),
    db: DbSession,
    params: Params,
    status_: Annotated[QuotationStatusLiteral | None, Query(alias="status")] = None,
    customer_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    data = QuotationService(db).list(
        params, status=status_, customer_id=customer_id, date_from=date_from, date_to=date_to
    )
    return ok(data, "Quotations retrieved")


@router.post(
    "",
    summary="Create a quotation",
    description="Prices and VAT default from the product; prices include VAT unless "
    "prices_include_tax=false. Valid for the quotation validity setting unless valid_until "
    "is given.",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[QuotationOut],
    responses=error_responses(400, *_E),
)
def create_quotation(
    body: QuotationCreate, ctx: auth_with(Perm.SALES_CREATE), db: DbSession
) -> dict:
    return ok(QuotationService(db).create(ctx, body), "Quotation created")


@router.get(
    "/{quotation_id}",
    summary="Get a quotation with its lines",
    response_model=ApiResponse[QuotationOut],
    responses=error_responses(404, *_E),
)
def get_quotation(quotation_id: uuid.UUID, ctx: auth_with(Perm.SALES_VIEW), db: DbSession) -> dict:
    return ok(QuotationService(db).get(quotation_id), "Quotation retrieved")


@router.put(
    "/{quotation_id}",
    summary="Update a draft or sent quotation",
    response_model=ApiResponse[QuotationOut],
    responses=error_responses(400, 404, *_E),
)
def update_quotation(
    quotation_id: uuid.UUID,
    body: QuotationUpdate,
    ctx: auth_with(Perm.SALES_UPDATE),
    db: DbSession,
) -> dict:
    return ok(QuotationService(db).update(ctx, quotation_id, body), "Quotation updated")


@router.delete(
    "/{quotation_id}",
    summary="Delete a draft quotation",
    response_model=ApiResponse[None],
    responses=error_responses(404, *_E),
)
def delete_quotation(
    quotation_id: uuid.UUID, ctx: auth_with(Perm.SALES_DELETE), db: DbSession
) -> dict:
    QuotationService(db).delete(ctx, quotation_id)
    return ok(None, "Quotation deleted")


@router.post(
    "/{quotation_id}/status",
    summary="Mark a quotation as sent, accepted or declined",
    response_model=ApiResponse[QuotationOut],
    responses=error_responses(404, *_E),
)
def set_quotation_status(
    quotation_id: uuid.UUID,
    body: QuotationStatusChange,
    ctx: auth_with(Perm.SALES_UPDATE),
    db: DbSession,
) -> dict:
    data = QuotationService(db).set_status(ctx, quotation_id, body.status)
    return ok(data, f"Quotation marked {body.status.lower()}")


@router.post(
    "/{quotation_id}/convert",
    summary="Convert a quotation into a draft invoice",
    description="Copies the customer, lines and prices. The quotation becomes CONVERTED.",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[InvoiceOut],
    responses=error_responses(404, *_E),
)
def convert_quotation(
    quotation_id: uuid.UUID,
    ctx: auth_with(Perm.SALES_CREATE),
    db: DbSession,
    body: ConvertQuotation | None = None,
) -> dict:
    data = QuotationService(db).convert(ctx, quotation_id, body or ConvertQuotation())
    return ok(data, "Draft invoice created from the quotation")


@router.get(
    "/{quotation_id}/pdf",
    summary="Download the quotation as a PDF",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "PDF document"},
        **error_responses(404, *_E),
    },
)
def quotation_pdf(
    quotation_id: uuid.UUID, ctx: auth_with(Perm.SALES_VIEW), db: DbSession
) -> Response:
    quotation = QuotationService(db).get(quotation_id)
    company = db.scalars(select(Company).limit(1)).first()
    footer = SettingsService(db).get("invoice_footer")
    pdf = render_quotation_pdf(quotation, company, footer)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{quotation.quote_number}.pdf"'},
    )
