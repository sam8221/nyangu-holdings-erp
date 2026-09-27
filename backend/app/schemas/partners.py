"""Customer, supplier, product category and product schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.utils.validators import clean_text, normalize_phone

CustomerType = Literal["INDIVIDUAL", "BUSINESS"]
ProductType = Literal["GOODS", "SERVICE"]

_MONEY = {"ge": 0, "max_digits": 14, "decimal_places": 2}


def _lower_email(v: str | None) -> str | None:
    return v.strip().lower() if v else None


def _sku(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip().upper()
    if not v or len(v) > 40 or not all(c.isalnum() or c in "-_./" for c in v):
        raise ValueError("SKU must be 1-40 characters: letters, digits, '-', '_', '.' or '/'")
    return v


# ---------------------------------------------------------------------- parties
class _PartyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    tpin: str | None
    email: str | None
    phone: str | None
    address: str | None
    city: str | None
    contact_person: str | None
    payment_terms_days: int
    is_active: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


class _PartyFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tpin: str | None = Field(default=None, pattern=r"^\d{10}$", description="10-digit ZRA TPIN")
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=1000)
    city: str | None = Field(default=None, max_length=100)
    contact_person: str | None = Field(default=None, max_length=150)
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    notes: str | None = Field(default=None, max_length=2000)

    _email = field_validator("email")(_lower_email)
    _phone = field_validator("phone")(normalize_phone)


class CustomerOut(_PartyOut):
    customer_type: str
    credit_limit: Decimal | None


class CustomerCreate(_PartyFields):
    name: str = Field(min_length=2, max_length=200)
    customer_type: CustomerType = "BUSINESS"
    credit_limit: Decimal | None = Field(default=None, description="Null means no limit", **_MONEY)

    _name = field_validator("name")(clean_text)


class CustomerUpdate(_PartyFields):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    customer_type: CustomerType | None = None
    credit_limit: Decimal | None = Field(default=None, **_MONEY)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return clean_text(v) if v is not None else None


class SupplierOut(_PartyOut):
    bank_name: str | None
    bank_branch: str | None
    bank_account_number: str | None


class _SupplierBank(BaseModel):
    bank_name: str | None = Field(default=None, max_length=100)
    bank_branch: str | None = Field(default=None, max_length=100)
    bank_account_number: str | None = Field(default=None, max_length=50)


class SupplierCreate(_PartyFields, _SupplierBank):
    name: str = Field(min_length=2, max_length=200)

    _name = field_validator("name")(clean_text)


class SupplierUpdate(_PartyFields, _SupplierBank):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return clean_text(v) if v is not None else None


# ---------------------------------------------------------------------- categories
class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=1000)

    _name = field_validator("name")(clean_text)


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return clean_text(v) if v is not None else None


# ---------------------------------------------------------------------- products
class CategoryRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str
    name: str
    description: str | None
    category: CategoryRef | None
    product_type: str
    unit: str
    barcode: str | None
    cost_price: Decimal
    selling_price: Decimal
    tax_rate: Decimal
    reorder_level: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime


class _ProductFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = Field(default=None, max_length=2000)
    category_id: uuid.UUID | None = None
    barcode: str | None = Field(default=None, max_length=50)
    reorder_level: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=3)

    @field_validator("barcode")
    @classmethod
    def _barcode(cls, v: str | None) -> str | None:
        return v.strip() or None if v else None


class ProductCreate(_ProductFields):
    sku: str = Field(min_length=1, max_length=40, examples=["CEM-50KG"])
    name: str = Field(min_length=2, max_length=200, examples=["Cement 50kg bag"])
    product_type: ProductType = "GOODS"
    unit: str = Field(default="pcs", min_length=1, max_length=20)
    cost_price: Decimal = Field(default=Decimal("0"), **_MONEY)
    selling_price: Decimal = Field(default=Decimal("0"), **_MONEY)
    tax_rate: Decimal | None = Field(
        default=None, ge=0, le=100, decimal_places=2, description="Defaults to the VAT setting"
    )

    _sku = field_validator("sku")(_sku)
    _name = field_validator("name")(clean_text)


class ProductUpdate(_ProductFields):
    sku: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, min_length=2, max_length=200)
    product_type: ProductType | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    selling_price: Decimal | None = Field(default=None, **_MONEY)
    tax_rate: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    is_active: bool | None = None

    _sku = field_validator("sku")(_sku)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return clean_text(v) if v is not None else None
