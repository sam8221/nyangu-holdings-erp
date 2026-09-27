"""Purchase order and goods receipt schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.sales import PartyRef, ProductRef

POStatusLiteral = Literal[
    "DRAFT", "APPROVED", "PARTIALLY_RECEIVED", "RECEIVED", "CLOSED", "CANCELLED"
]
_MONEY = {"max_digits": 14, "decimal_places": 2}
_QTY = {"max_digits": 14, "decimal_places": 3}
_RATE = {"ge": 0, "le": 100, "max_digits": 5, "decimal_places": 2}


class WarehouseRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str


class POLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: uuid.UUID
    quantity: Decimal = Field(gt=0, **_QTY)
    unit_cost: Decimal | None = Field(
        default=None, ge=0, description="Defaults to the product's current cost", **_MONEY
    )
    tax_rate: Decimal | None = Field(default=None, description="Defaults to the product's", **_RATE)
    description: str | None = Field(default=None, max_length=300)


def _check(
    order_date: date | None, expected_date: date | None, lines: list[POLineIn] | None
) -> None:
    if order_date and expected_date and expected_date < order_date:
        raise ValueError("expected_date cannot be before order_date")
    if lines:
        ids = [ln.product_id for ln in lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Each product may appear only once per order")


class POCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: uuid.UUID
    warehouse_id: uuid.UUID = Field(description="Where the goods will be delivered")
    branch_id: uuid.UUID | None = None
    order_date: date | None = Field(default=None, description="Defaults to today")
    expected_date: date | None = None
    supplier_reference: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[POLineIn] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _validate(self) -> POCreate:
        _check(self.order_date, self.expected_date, self.lines)
        return self


class POUpdate(BaseModel):
    """Drafts only. ``lines``, when sent, replaces every line."""

    model_config = ConfigDict(extra="forbid")

    supplier_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    order_date: date | None = None
    expected_date: date | None = None
    supplier_reference: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[POLineIn] | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _validate(self) -> POUpdate:
        _check(self.order_date, self.expected_date, self.lines)
        return self


class POLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_no: int
    product: ProductRef
    description: str
    quantity: Decimal
    unit_cost: Decimal
    tax_rate: Decimal
    line_subtotal: Decimal
    line_tax: Decimal
    line_total: Decimal
    received_quantity: Decimal
    outstanding_quantity: Decimal


class GRNLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    purchase_order_line_id: uuid.UUID
    product: ProductRef
    quantity: Decimal
    unit_cost: Decimal


class GRNOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    grn_number: str
    purchase_order_id: uuid.UUID
    po_number: str
    warehouse: WarehouseRef
    received_date: date
    delivery_note: str | None
    notes: str | None
    received_by_id: uuid.UUID | None
    created_at: datetime
    lines: list[GRNLineOut]


class _POBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    po_number: str
    supplier: PartyRef
    warehouse: WarehouseRef
    branch_id: uuid.UUID | None
    order_date: date
    expected_date: date | None
    status: str
    currency: str
    supplier_reference: str | None
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    received_value: Decimal
    created_at: datetime
    updated_at: datetime


class POSummary(_POBase):
    pass


class POOut(_POBase):
    notes: str | None
    created_by_id: uuid.UUID | None
    approved_by_id: uuid.UUID | None
    approved_at: datetime | None
    cancelled_by_id: uuid.UUID | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    lines: list[POLineOut]
    receipts: list[GRNOut]


class GRNLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purchase_order_line_id: uuid.UUID
    quantity: Decimal = Field(gt=0, **_QTY)
    unit_cost: Decimal | None = Field(
        default=None, ge=0, description="Defaults to the order line's cost", **_MONEY
    )


class GRNCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purchase_order_id: uuid.UUID
    warehouse_id: uuid.UUID | None = Field(
        default=None, description="Defaults to the order's delivery warehouse"
    )
    received_date: date | None = Field(default=None, description="Defaults to today")
    delivery_note: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[GRNLineIn] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _unique(self) -> GRNCreate:
        ids = [ln.purchase_order_line_id for ln in self.lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Each order line may appear only once per receipt")
        return self
