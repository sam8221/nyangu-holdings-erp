"""Sales invoice and customer payment schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

InvoiceStatusLiteral = Literal["DRAFT", "ISSUED", "PARTIALLY_PAID", "PAID", "CANCELLED"]
PaymentMethod = Literal["CASH", "BANK_TRANSFER", "MOBILE_MONEY", "CHEQUE", "CARD"]

_MONEY = {"max_digits": 14, "decimal_places": 2}
_QTY = {"max_digits": 14, "decimal_places": 3}
_RATE = {"ge": 0, "le": 100, "max_digits": 5, "decimal_places": 2}


class PartyRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str


class ProductRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str
    name: str
    unit: str


class InvoiceLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: uuid.UUID
    quantity: Decimal = Field(gt=0, **_QTY)
    unit_price: Decimal | None = Field(
        default=None, ge=0, description="Defaults to the product's selling price", **_MONEY
    )
    discount_percent: Decimal = Field(default=Decimal("0"), **_RATE)
    tax_rate: Decimal | None = Field(
        default=None, description="Defaults to the product's tax rate", **_RATE
    )
    description: str | None = Field(default=None, max_length=300)


def _check_dates(invoice_date: date | None, due_date: date | None) -> None:
    if invoice_date and due_date and due_date < invoice_date:
        raise ValueError("due_date cannot be before invoice_date")


class InvoiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = Field(
        default=None, description="Required when the invoice contains goods"
    )
    invoice_date: date | None = Field(default=None, description="Defaults to today")
    due_date: date | None = Field(default=None, description="Defaults to the customer's terms")
    customer_reference: str | None = Field(default=None, max_length=100)
    prices_include_tax: bool | None = Field(
        default=None, description="Unit prices include VAT. Defaults to the system setting"
    )
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[InvoiceLineIn] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _dates(self) -> InvoiceCreate:
        _check_dates(self.invoice_date, self.due_date)
        return self


class InvoiceUpdate(BaseModel):
    """Drafts only. ``lines``, when sent, replaces every line."""

    model_config = ConfigDict(extra="forbid")

    customer_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    customer_reference: str | None = Field(default=None, max_length=100)
    prices_include_tax: bool | None = Field(
        default=None, description="Unit prices include VAT. Defaults to the system setting"
    )
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[InvoiceLineIn] | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _dates(self) -> InvoiceUpdate:
        _check_dates(self.invoice_date, self.due_date)
        return self


class InvoiceLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_no: int
    product: ProductRef
    description: str
    quantity: Decimal
    unit_price: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    tax_rate: Decimal
    line_subtotal: Decimal
    line_tax: Decimal
    line_total: Decimal


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    receipt_number: str
    customer: PartyRef
    invoice_id: uuid.UUID
    invoice_number: str | None
    amount: Decimal
    payment_date: date
    method: str
    reference: str | None
    notes: str | None
    status: str
    received_by_id: uuid.UUID | None
    voided_by_id: uuid.UUID | None
    voided_at: datetime | None
    void_reason: str | None
    created_at: datetime


class _InvoiceBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str | None
    customer: PartyRef
    branch_id: uuid.UUID | None
    warehouse_id: uuid.UUID | None
    invoice_date: date
    due_date: date
    status: str
    currency: str
    prices_include_tax: bool
    customer_reference: str | None
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    total: Decimal
    amount_paid: Decimal
    balance_due: Decimal
    is_overdue: bool
    created_at: datetime
    updated_at: datetime


class InvoiceSummary(_InvoiceBase):
    """List view: no lines or payments."""


class InvoiceOut(_InvoiceBase):
    notes: str | None
    created_by_id: uuid.UUID | None
    approved_by_id: uuid.UUID | None
    approved_at: datetime | None
    cancelled_by_id: uuid.UUID | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    lines: list[InvoiceLineOut]
    payments: list[PaymentOut]


class CancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=1000)


class PaymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=0, **_MONEY)
    payment_date: date | None = Field(default=None, description="Defaults to today")
    method: PaymentMethod
    reference: str | None = Field(default=None, max_length=100, examples=["MTN-8XK2PQ"])
    notes: str | None = Field(default=None, max_length=1000)


# ---------------------------------------------------------------------- quotations
QuotationStatusLiteral = Literal["DRAFT", "SENT", "ACCEPTED", "DECLINED", "CONVERTED"]


def _check_validity(quote_date: date | None, valid_until: date | None) -> None:
    if quote_date and valid_until and valid_until < quote_date:
        raise ValueError("valid_until cannot be before quote_date")


class QuotationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    quote_date: date | None = Field(default=None, description="Defaults to today")
    valid_until: date | None = Field(
        default=None, description="Defaults to quote_date + the quotation validity setting"
    )
    customer_reference: str | None = Field(default=None, max_length=100)
    prices_include_tax: bool | None = Field(
        default=None, description="Unit prices include VAT. Defaults to the system setting"
    )
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[InvoiceLineIn] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _dates(self) -> QuotationCreate:
        _check_validity(self.quote_date, self.valid_until)
        return self


class QuotationUpdate(BaseModel):
    """Drafts and sent quotations. ``lines``, when sent, replaces every line."""

    model_config = ConfigDict(extra="forbid")

    customer_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    quote_date: date | None = None
    valid_until: date | None = None
    customer_reference: str | None = Field(default=None, max_length=100)
    prices_include_tax: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[InvoiceLineIn] | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _dates(self) -> QuotationUpdate:
        _check_validity(self.quote_date, self.valid_until)
        return self


class _QuotationBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    quote_number: str
    customer: PartyRef
    branch_id: uuid.UUID | None
    quote_date: date
    valid_until: date
    status: str
    is_expired: bool
    currency: str
    prices_include_tax: bool
    customer_reference: str | None
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    total: Decimal
    invoice_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class QuotationSummary(_QuotationBase):
    """List view: no lines."""


class QuotationOut(_QuotationBase):
    notes: str | None
    created_by_id: uuid.UUID | None
    lines: list[InvoiceLineOut]


class QuotationStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["SENT", "ACCEPTED", "DECLINED"]


class ConvertQuotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warehouse_id: uuid.UUID | None = Field(
        default=None, description="Warehouse the goods will be issued from"
    )
    invoice_date: date | None = Field(default=None, description="Defaults to today")
