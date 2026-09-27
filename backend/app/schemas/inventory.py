"""Warehouse and stock schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.utils.validators import clean_text, normalize_code

MovementTypeLiteral = Literal[
    "RECEIPT", "SALE", "SALE_REVERSAL", "ADJUSTMENT", "TRANSFER_OUT", "TRANSFER_IN"
]
_QTY = {"max_digits": 14, "decimal_places": 3}


class Ref(BaseModel):
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


class WarehouseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    branch: Ref | None
    address: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WarehouseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=20, examples=["LSK-MAIN"])
    name: str = Field(min_length=2, max_length=150, examples=["Lusaka main store"])
    branch_id: uuid.UUID | None = None
    address: str | None = Field(default=None, max_length=1000)

    _code = field_validator("code")(normalize_code)
    _name = field_validator("name")(clean_text)


class WarehouseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(default=None, min_length=1, max_length=20)
    name: str | None = Field(default=None, min_length=2, max_length=150)
    branch_id: uuid.UUID | None = None
    address: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None

    @field_validator("code")
    @classmethod
    def _code(cls, v: str | None) -> str | None:
        return normalize_code(v) if v is not None else None


class StockLevelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product: ProductRef
    warehouse: Ref
    quantity: Decimal
    updated_at: datetime


class WarehouseQuantity(BaseModel):
    warehouse_id: uuid.UUID
    code: str
    name: str
    quantity: Decimal


class ProductStockOut(BaseModel):
    product_id: uuid.UUID
    sku: str
    name: str
    unit: str
    reorder_level: Decimal
    total_quantity: Decimal
    is_low: bool
    stock_value: Decimal = Field(description="Quantity x weighted average cost")
    warehouses: list[WarehouseQuantity]


class LowStockItem(BaseModel):
    product_id: uuid.UUID
    sku: str
    name: str
    unit: str
    on_hand: Decimal
    reorder_level: Decimal
    shortfall: Decimal


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product: ProductRef
    warehouse: Ref
    movement_type: str
    quantity: Decimal
    balance_after: Decimal
    unit_cost: Decimal
    reference_type: str | None
    reference_id: uuid.UUID | None
    reference_number: str | None
    notes: str | None
    created_by_id: uuid.UUID | None
    created_at: datetime


class AdjustmentLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: uuid.UUID
    quantity_change: Decimal | None = Field(
        default=None, description="Signed change, e.g. -2 for breakage", **_QTY
    )
    counted_quantity: Decimal | None = Field(
        default=None, ge=0, description="Physical count; the system works out the change", **_QTY
    )

    @model_validator(mode="after")
    def _one_of(self) -> AdjustmentLine:
        if (self.quantity_change is None) == (self.counted_quantity is None):
            raise ValueError("Give exactly one of quantity_change or counted_quantity")
        if self.quantity_change is not None and self.quantity_change == 0:
            raise ValueError("quantity_change cannot be zero")
        return self


class AdjustmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warehouse_id: uuid.UUID
    reason: str = Field(min_length=3, max_length=500, examples=["Monthly stock count"])
    lines: list[AdjustmentLine] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _unique_products(self) -> AdjustmentCreate:
        ids = [line.product_id for line in self.lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Each product may appear only once")
        return self


class TransferLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: uuid.UUID
    quantity: Decimal = Field(gt=0, **_QTY)


class TransferCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_warehouse_id: uuid.UUID
    to_warehouse_id: uuid.UUID
    notes: str | None = Field(default=None, max_length=500)
    lines: list[TransferLine] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _unique_products(self) -> TransferCreate:
        ids = [line.product_id for line in self.lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Each product may appear only once")
        return self


class StockOperationResult(BaseModel):
    reference_number: str
    movements: list[MovementOut]
