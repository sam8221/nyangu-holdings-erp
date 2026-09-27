"""Employees and leave requests."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.organization import Branch, Department


class EmployeeStatus:
    ACTIVE = "ACTIVE"
    ON_LEAVE = "ON_LEAVE"
    SUSPENDED = "SUSPENDED"
    TERMINATED = "TERMINATED"
    ALL = (ACTIVE, ON_LEAVE, SUSPENDED, TERMINATED)


EMPLOYMENT_TYPES = ("PERMANENT", "CONTRACT", "CASUAL", "INTERN")
GENDERS = ("MALE", "FEMALE", "OTHER")


class Employee(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'ON_LEAVE', 'SUSPENDED', 'TERMINATED')", name="status_valid"
        ),
        CheckConstraint(
            "employment_type IN ('PERMANENT', 'CONTRACT', 'CASUAL', 'INTERN')",
            name="employment_type_valid",
        ),
        CheckConstraint("basic_salary IS NULL OR basic_salary >= 0", name="salary_non_negative"),
        CheckConstraint(
            "termination_date IS NULL OR termination_date >= hire_date",
            name="termination_after_hire",
        ),
        Index("ix_employees_name", "last_name", "first_name"),
    )

    employee_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_name: Mapped[str] = mapped_column(String(80), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    national_id: Mapped[str | None] = mapped_column(String(30), unique=True, nullable=True)  # NRC
    napsa_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    tpin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)

    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("branches.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("departments.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), unique=True, nullable=True
    )

    job_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    employment_type: Mapped[str] = mapped_column(String(20), nullable=False, default="PERMANENT")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EmployeeStatus.ACTIVE, index=True
    )
    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    termination_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Visible only with employees.view_salary.
    basic_salary: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(String(50), nullable=True)

    emergency_contact_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)

    branch: Mapped[Branch | None] = relationship(lazy="joined")
    department: Mapped[Department | None] = relationship(lazy="joined")

    @property
    def full_name(self) -> str:
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(p for p in parts if p)


class LeaveStatus:
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    ALL = (PENDING, APPROVED, REJECTED, CANCELLED)
    OPEN = (PENDING, APPROVED)


LEAVE_TYPES = ("ANNUAL", "SICK", "MATERNITY", "PATERNITY", "COMPASSIONATE", "STUDY", "UNPAID")


class LeaveRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "leave_requests"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="dates_ordered"),
        CheckConstraint("days > 0", name="days_positive"),
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED')", name="status_valid"
        ),
        Index("ix_leave_requests_employee_dates", "employee_id", "start_date", "end_date"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    leave_type: Mapped[str] = mapped_column(String(20), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    days: Mapped[Decimal] = mapped_column(Numeric(5, 1), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=LeaveStatus.PENDING, index=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    employee: Mapped[Employee] = relationship(lazy="joined")

    @property
    def employee_name(self) -> str:
        return self.employee.full_name

    @property
    def employee_number(self) -> str:
        return self.employee.employee_number
