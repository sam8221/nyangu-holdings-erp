"""Asset and asset category schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.utils.validators import clean_text

Method = Literal["STRAIGHT_LINE", "NONE"]
ActiveStatus = Literal["IN_USE", "IN_STORE", "UNDER_MAINTENANCE"]
_MONEY = {"ge": 0, "max_digits": 14, "decimal_places": 2}


class AssetCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    depreciation_method: str
    useful_life_months: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AssetCategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=100, examples=["Motor vehicles"])
    description: str | None = Field(default=None, max_length=1000)
    depreciation_method: Method = "STRAIGHT_LINE"
    useful_life_months: int = Field(default=60, gt=0, le=1200)

    _name = field_validator("name")(clean_text)


class AssetCategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    depreciation_method: Method | None = None
    useful_life_months: int | None = Field(default=None, gt=0, le=1200)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return clean_text(v) if v is not None else None


class Ref(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class BranchRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str


class EmployeeRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_number: str
    full_name: str


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_tag: str
    name: str
    category: Ref
    branch: BranchRef | None
    assigned_employee: EmployeeRef | None
    supplier_id: uuid.UUID | None
    serial_number: str | None
    location: str | None
    purchase_date: date
    purchase_cost: Decimal
    salvage_value: Decimal
    depreciation_method: str
    useful_life_months: int
    accumulated_depreciation: Decimal
    book_value: Decimal
    status: str
    notes: str | None
    disposal_date: date | None
    disposal_value: Decimal | None
    disposal_reason: str | None
    disposal_gain_loss: Decimal | None
    created_at: datetime
    updated_at: datetime


class _AssetFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    serial_number: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("serial_number")
    @classmethod
    def _serial(cls, v: str | None) -> str | None:
        return v.strip().upper() or None if v else None


class AssetCreate(_AssetFields):
    name: str = Field(min_length=2, max_length=200, examples=["Toyota Hilux ABC 1234"])
    category_id: uuid.UUID
    purchase_date: date
    purchase_cost: Decimal = Field(**_MONEY)
    salvage_value: Decimal = Field(default=Decimal("0"), **_MONEY)
    depreciation_method: Method | None = Field(default=None, description="Defaults to category")
    useful_life_months: int | None = Field(
        default=None, gt=0, le=1200, description="Defaults to category"
    )
    status: ActiveStatus = "IN_USE"

    _name = field_validator("name")(clean_text)

    @model_validator(mode="after")
    def _salvage(self) -> AssetCreate:
        if self.salvage_value > self.purchase_cost:
            raise ValueError("salvage_value cannot exceed purchase_cost")
        return self


class AssetUpdate(_AssetFields):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    category_id: uuid.UUID | None = None
    purchase_date: date | None = None
    purchase_cost: Decimal | None = Field(default=None, **_MONEY)
    salvage_value: Decimal | None = Field(default=None, **_MONEY)
    depreciation_method: Method | None = None
    useful_life_months: int | None = Field(default=None, gt=0, le=1200)
    status: ActiveStatus | None = Field(default=None, description="Use dispose to dispose")

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return clean_text(v) if v is not None else None


class AssetAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: uuid.UUID | None = Field(description="Null returns the asset to store")
    location: str | None = Field(default=None, max_length=200)


class AssetDispose(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disposal_date: date
    disposal_value: Decimal = Field(description="Sale proceeds; 0 for a write-off", **_MONEY)
    reason: str = Field(min_length=3, max_length=1000)


class DepreciationYear(BaseModel):
    year: int
    opening_value: Decimal
    depreciation: Decimal
    closing_value: Decimal


class DepreciationSchedule(BaseModel):
    asset_id: uuid.UUID
    asset_tag: str
    method: str
    monthly_depreciation: Decimal
    years: list[DepreciationYear]
