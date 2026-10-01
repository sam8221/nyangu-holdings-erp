"""Company, branch, department and settings schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.utils.validators import clean_text, normalize_code, normalize_phone


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    legal_name: str | None
    registration_number: str | None
    tpin: str | None
    vat_number: str | None
    email: str | None
    phone: str | None
    website: str | None
    address: str | None
    city: str | None
    country: str
    currency: str
    fiscal_year_start_month: int
    updated_at: datetime


class CompanyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=150)
    legal_name: str | None = Field(default=None, max_length=200)
    registration_number: str | None = Field(default=None, max_length=50)
    tpin: str | None = Field(
        default=None, pattern=r"^\d{10,11}$", description="ZRA TPIN (10 or 11 digits)"
    )
    vat_number: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    website: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=1000)
    city: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, min_length=2, max_length=100)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    fiscal_year_start_month: int | None = Field(default=None, ge=1, le=12)

    _phone = field_validator("phone")(normalize_phone)


class BranchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    address: str | None
    city: str | None
    phone: str | None
    email: str | None
    is_head_office: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class BranchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=20, examples=["LSK"])
    name: str = Field(min_length=2, max_length=150, examples=["Lusaka Main"])
    address: str | None = Field(default=None, max_length=1000)
    city: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    is_head_office: bool = False

    _code = field_validator("code")(normalize_code)
    _name = field_validator("name")(clean_text)
    _phone = field_validator("phone")(normalize_phone)


class BranchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(default=None, min_length=1, max_length=20)
    name: str | None = Field(default=None, min_length=2, max_length=150)
    address: str | None = Field(default=None, max_length=1000)
    city: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    is_head_office: bool | None = None
    is_active: bool | None = None

    @field_validator("code")
    @classmethod
    def _code(cls, v: str | None) -> str | None:
        return normalize_code(v) if v is not None else None

    _phone = field_validator("phone")(normalize_phone)


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DepartmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=20, examples=["FIN"])
    name: str = Field(min_length=2, max_length=150, examples=["Finance"])
    description: str | None = Field(default=None, max_length=1000)

    _code = field_validator("code")(normalize_code)
    _name = field_validator("name")(clean_text)


class DepartmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(default=None, min_length=1, max_length=20)
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None

    @field_validator("code")
    @classmethod
    def _code(cls, v: str | None) -> str | None:
        return normalize_code(v) if v is not None else None


class SettingsOut(BaseModel):
    default_vat_rate: Decimal = Field(description="Percent applied to new products, e.g. 16.00")
    default_payment_terms_days: int
    annual_leave_days: int = Field(description="Annual leave entitlement per calendar year")
    low_stock_alerts_enabled: bool
    invoice_footer: str
    prices_include_tax: bool = Field(
        description="Prices on new quotations and invoices include VAT"
    )
    quotation_validity_days: int


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_vat_rate: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    default_payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    annual_leave_days: int | None = Field(default=None, ge=0, le=366)
    low_stock_alerts_enabled: bool | None = None
    invoice_footer: str | None = Field(default=None, max_length=500)
    prices_include_tax: bool | None = None
    quotation_validity_days: int | None = Field(default=None, ge=1, le=365)
