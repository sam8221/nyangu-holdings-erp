"""Expenses, supplier bills (payables) and supplier payments."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.partners import Supplier
from app.utils.time import local_today

_METHODS = "method IN ('CASH', 'BANK_TRANSFER', 'MOBILE_MONEY', 'CHEQUE', 'CARD')"


class ExpenseCategory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "expense_categories"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ExpenseStatus:
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Expense(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount > 0 AND tax_amount >= 0", name="amounts_valid"),
        CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED')", name="status_valid"),
        CheckConstraint(f"method IS NULL OR {_METHODS}", name="method_valid"),
    )

    expense_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("expense_categories.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True
    )
    expense_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    payee: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)  # before tax
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(10), index=True, nullable=False, default="PENDING")
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    category: Mapped[ExpenseCategory] = relationship(lazy="joined")

    @property
    def total(self) -> Decimal:
        return self.amount + self.tax_amount


class BillStatus:
    PENDING = "PENDING"  # awaiting approval
    APPROVED = "APPROVED"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    CANCELLED = "CANCELLED"
    OPEN = (APPROVED, PARTIALLY_PAID)


class SupplierBill(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "supplier_bills"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'PARTIALLY_PAID', 'PAID', 'CANCELLED')",
            name="status_valid",
        ),
        CheckConstraint("due_date >= bill_date", name="due_after_bill"),
        CheckConstraint("subtotal >= 0 AND tax_total >= 0 AND total > 0", name="amounts_valid"),
        CheckConstraint("amount_paid >= 0 AND amount_paid <= total", name="paid_within_total"),
        UniqueConstraint(
            "supplier_id", "supplier_invoice_number", name="uq_supplier_bills_supplier_invoice"
        ),
        Index("ix_supplier_bills_supplier_status", "supplier_id", "status"),
    )

    bill_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False
    )
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("purchase_orders.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    supplier_invoice_number: Mapped[str] = mapped_column(String(100), nullable=False)
    bill_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False, default="PENDING")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="ZMW")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    supplier: Mapped[Supplier] = relationship(lazy="joined")
    payments: Mapped[list[SupplierPayment]] = relationship(
        back_populates="bill", order_by="SupplierPayment.payment_number", lazy="selectin"
    )

    @property
    def balance_due(self) -> Decimal:
        return self.total - self.amount_paid

    @property
    def is_overdue(self) -> bool:
        return self.status in BillStatus.OPEN and self.due_date < local_today()


class SupplierPayment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "supplier_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("status IN ('POSTED', 'VOIDED')", name="status_valid"),
        CheckConstraint(_METHODS, name="method_valid"),
    )

    payment_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    bill_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("supplier_bills.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="POSTED")
    paid_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    bill: Mapped[SupplierBill] = relationship(back_populates="payments")
    supplier: Mapped[Supplier] = relationship(lazy="joined")

    @property
    def bill_number(self) -> str:
        return self.bill.bill_number
