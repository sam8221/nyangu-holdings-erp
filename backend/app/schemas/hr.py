"""Employee and leave schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.utils.validators import clean_text, normalize_phone

EmploymentType = Literal["PERMANENT", "CONTRACT", "CASUAL", "INTERN"]
Gender = Literal["MALE", "FEMALE", "OTHER"]
EmployeeStatusLiteral = Literal["ACTIVE", "ON_LEAVE", "SUSPENDED", "TERMINATED"]
LeaveType = Literal["ANNUAL", "SICK", "MATERNITY", "PATERNITY", "COMPASSIONATE", "STUDY", "UNPAID"]
LeaveStatusLiteral = Literal["PENDING", "APPROVED", "REJECTED", "CANCELLED"]

Money = Decimal


class RefOut(BaseModel):
    """A compact reference to a related record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str


class EmployeeOut(BaseModel):
    """Salary and bank fields are null unless the caller holds employees.view_salary."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_number: str
    first_name: str
    middle_name: str | None
    last_name: str
    full_name: str
    gender: str | None
    date_of_birth: date | None
    national_id: str | None
    napsa_number: str | None
    tpin: str | None
    email: str | None
    phone: str | None
    address: str | None
    branch: RefOut | None
    department: RefOut | None
    manager_id: uuid.UUID | None
    user_id: uuid.UUID | None
    job_title: str | None
    employment_type: str
    status: str
    hire_date: date
    termination_date: date | None
    termination_reason: str | None
    basic_salary: Money | None
    bank_name: str | None
    bank_account_number: str | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    created_at: datetime
    updated_at: datetime


SALARY_FIELDS = ("basic_salary", "bank_name", "bank_account_number")


class _EmployeeFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    middle_name: str | None = Field(default=None, max_length=80)
    gender: Gender | None = None
    date_of_birth: date | None = None
    national_id: str | None = Field(
        default=None, max_length=30, description="NRC, e.g. 123456/10/1", examples=["123456/10/1"]
    )
    napsa_number: str | None = Field(default=None, max_length=30)
    tpin: str | None = Field(default=None, pattern=r"^\d{10,11}$")
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=1000)
    branch_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    job_title: str | None = Field(default=None, max_length=120)
    basic_salary: Money | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    bank_name: str | None = Field(default=None, max_length=100)
    bank_account_number: str | None = Field(default=None, max_length=50)
    emergency_contact_name: str | None = Field(default=None, max_length=150)
    emergency_contact_phone: str | None = Field(default=None, max_length=30)

    _phones = field_validator("phone", "emergency_contact_phone")(normalize_phone)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        return v.strip().lower() if v else None

    @field_validator("national_id")
    @classmethod
    def _nrc(cls, v: str | None) -> str | None:
        return v.strip().upper() if v and v.strip() else None

    @field_validator("date_of_birth")
    @classmethod
    def _dob(cls, v: date | None) -> date | None:
        if v and v > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return v


class EmployeeCreate(_EmployeeFields):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    employment_type: EmploymentType = "PERMANENT"
    hire_date: date

    _names = field_validator("first_name", "last_name")(clean_text)


class EmployeeUpdate(_EmployeeFields):
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=80)
    employment_type: EmploymentType | None = None
    hire_date: date | None = None
    status: Literal["ACTIVE", "ON_LEAVE", "SUSPENDED"] | None = Field(
        default=None, description="Use the terminate endpoint to terminate"
    )

    @field_validator("first_name", "last_name")
    @classmethod
    def _names(cls, v: str | None) -> str | None:
        return clean_text(v) if v is not None else None


class EmployeeTerminate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    termination_date: date
    reason: str = Field(min_length=3, max_length=1000)


class LeaveBalance(BaseModel):
    employee_id: uuid.UUID
    year: int
    entitlement: Decimal
    taken: Decimal
    pending: Decimal
    remaining: Decimal


class LeaveRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    employee_number: str
    leave_type: str
    start_date: date
    end_date: date
    days: Decimal
    reason: str | None
    status: str
    created_by_id: uuid.UUID | None
    reviewed_by_id: uuid.UUID | None
    reviewed_at: datetime | None
    review_comment: str | None
    created_at: datetime
    updated_at: datetime


class LeaveRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: uuid.UUID
    leave_type: LeaveType
    start_date: date
    end_date: date
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _dates(self) -> LeaveRequestCreate:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("A single leave request cannot exceed one year")
        return self


class LeaveDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=1000)


class LeaveRejection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str = Field(min_length=3, max_length=1000)
