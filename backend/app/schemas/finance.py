"""Finance schemas: expenses, supplier bills and payments, receivables, payables, statements."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.sales import PartyRef, PaymentMethod
from app.utils.validators import clean_text

ExpenseStatusLiteral = Literal["PENDING", "APPROVED", "REJECTED"]
BillStatusLiteral = Literal["PENDING", "APPROVED", "PARTIALLY_PAID", "PAID", "CANCELLED"]
_MONEY = {"max_digits": 14, "decimal_places": 2}


# ---------------------------------------------------------------------- expense categories
class ExpenseCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ExpenseCategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=100, examples=["Fuel"])
    description: str | None = Field(default=None, max_length=1000)

    _name = field_validator("name")(clean_text)


class ExpenseCategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return clean_text(v) if v is not None else None


# ---------------------------------------------------------------------- expenses
class CategoryRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    expense_number: str
    category: CategoryRef
    branch_id: uuid.UUID | None
    expense_date: date
    payee: str
    description: str
    amount: Decimal
    tax_amount: Decimal
    total: Decimal
    method: str | None
    reference: str | None
    status: str
    submitted_by_id: uuid.UUID | None
    reviewed_by_id: uuid.UUID | None
    reviewed_at: datetime | None
    review_comment: str | None
    created_at: datetime
    updated_at: datetime


class ExpenseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    expense_date: date | None = Field(default=None, description="Defaults to today")
    payee: str = Field(min_length=2, max_length=200, examples=["Puma Energy"])
    description: str = Field(min_length=3, max_length=2000)
    amount: Decimal = Field(gt=0, description="Amount before tax", **_MONEY)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0, **_MONEY)
    method: PaymentMethod | None = None
    reference: str | None = Field(default=None, max_length=100)


class ExpenseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    expense_date: date | None = None
    payee: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, min_length=3, max_length=2000)
    amount: Decimal | None = Field(default=None, gt=0, **_MONEY)
    tax_amount: Decimal | None = Field(default=None, ge=0, **_MONEY)
    method: PaymentMethod | None = None
    reference: str | None = Field(default=None, max_length=100)


class ReviewComment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=1000)


class RejectComment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str = Field(min_length=3, max_length=1000)


# ---------------------------------------------------------------------- supplier bills
class SupplierPaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    payment_number: str
    supplier: PartyRef
    bill_id: uuid.UUID
    bill_number: str
    amount: Decimal
    payment_date: date
    method: str
    reference: str | None
    notes: str | None
    status: str
    paid_by_id: uuid.UUID | None
    voided_by_id: uuid.UUID | None
    voided_at: datetime | None
    void_reason: str | None
    created_at: datetime


class _BillBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bill_number: str
    supplier: PartyRef
    purchase_order_id: uuid.UUID | None
    supplier_invoice_number: str
    bill_date: date
    due_date: date
    status: str
    currency: str
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    amount_paid: Decimal
    balance_due: Decimal
    is_overdue: bool
    created_at: datetime
    updated_at: datetime


class BillSummary(_BillBase):
    pass


class BillOut(_BillBase):
    notes: str | None
    created_by_id: uuid.UUID | None
    approved_by_id: uuid.UUID | None
    approved_at: datetime | None
    cancelled_by_id: uuid.UUID | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    payments: list[SupplierPaymentOut]


class BillCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: uuid.UUID
    purchase_order_id: uuid.UUID | None = None
    supplier_invoice_number: str = Field(min_length=1, max_length=100, examples=["LZ-INV-4471"])
    bill_date: date | None = Field(default=None, description="Defaults to today")
    due_date: date | None = Field(default=None, description="Defaults to the supplier's terms")
    subtotal: Decimal = Field(ge=0, **_MONEY)
    tax_total: Decimal = Field(default=Decimal("0"), ge=0, **_MONEY)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _check(self) -> BillCreate:
        if self.subtotal + self.tax_total <= 0:
            raise ValueError("The bill total must be greater than zero")
        if self.bill_date and self.due_date and self.due_date < self.bill_date:
            raise ValueError("due_date cannot be before bill_date")
        return self


class SupplierPaymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=0, **_MONEY)
    payment_date: date | None = Field(default=None, description="Defaults to today")
    method: PaymentMethod
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)


# ---------------------------------------------------------------------- aging and statements
class AgingBuckets(BaseModel):
    current: Decimal = Field(description="Not yet due")
    days_1_30: Decimal
    days_31_60: Decimal
    days_61_90: Decimal
    days_over_90: Decimal
    total: Decimal


class AgingRow(AgingBuckets):
    party: PartyRef
    documents: int


class AgingReport(BaseModel):
    as_of: date
    rows: list[AgingRow]
    totals: AgingBuckets


class StatementLine(BaseModel):
    date: date
    type: Literal["INVOICE", "PAYMENT"]
    reference: str
    description: str
    debit: Decimal
    credit: Decimal
    balance: Decimal


class CustomerStatement(BaseModel):
    customer: PartyRef
    date_from: date
    date_to: date
    opening_balance: Decimal
    lines: list[StatementLine]
    closing_balance: Decimal
