"""Sales invoices, their lines and customer payments (receipts)."""

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
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.inventory import Warehouse
from app.models.organization import Branch
from app.models.partners import Customer, Product
from app.utils.time import local_today


class InvoiceStatus:
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    CANCELLED = "CANCELLED"
    ALL = (DRAFT, ISSUED, PARTIALLY_PAID, PAID, CANCELLED)
    OPEN = (ISSUED, PARTIALLY_PAID)  # money still owed
    POSTED = (ISSUED, PARTIALLY_PAID, PAID)  # counts as revenue


class SalesInvoice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sales_invoices"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'ISSUED', 'PARTIALLY_PAID', 'PAID', 'CANCELLED')",
            name="status_valid",
        ),
        CheckConstraint("due_date >= invoice_date", name="due_after_invoice"),
        CheckConstraint("amount_paid >= 0 AND amount_paid <= total", name="paid_within_total"),
        Index("ix_sales_invoices_customer_status", "customer_id", "status"),
    )

    # Assigned when the invoice is issued, so issued numbers have no gaps.
    invoice_number: Mapped[str | None] = mapped_column(String(30), unique=True, nullable=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True
    )
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True
    )
    invoice_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=InvoiceStatus.DRAFT, index=True
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="ZMW")
    customer_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    discount_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)

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

    customer: Mapped[Customer] = relationship(lazy="joined")
    branch: Mapped[Branch | None] = relationship(lazy="joined")
    warehouse: Mapped[Warehouse | None] = relationship(lazy="joined")
    lines: Mapped[list[SalesInvoiceLine]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="SalesInvoiceLine.line_no",
        lazy="selectin",
    )
    payments: Mapped[list[CustomerPayment]] = relationship(
        back_populates="invoice", order_by="CustomerPayment.receipt_number", lazy="selectin"
    )

    @property
    def balance_due(self) -> Decimal:
        return self.total - self.amount_paid

    @property
    def is_overdue(self) -> bool:
        return self.status in InvoiceStatus.OPEN and self.due_date < local_today()


class SalesInvoiceLine(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sales_invoice_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="price_non_negative"),
        CheckConstraint("discount_percent >= 0 AND discount_percent <= 100", name="discount_valid"),
    )

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sales_invoices.id", ondelete="CASCADE"), index=True, nullable=False
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    line_subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    line_tax: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # Weighted average cost captured when issued; used for cost of sales.
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    invoice: Mapped[SalesInvoice] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship(lazy="joined")


class PaymentStatus:
    POSTED = "POSTED"
    VOIDED = "VOIDED"


PAYMENT_METHODS = ("CASH", "BANK_TRANSFER", "MOBILE_MONEY", "CHEQUE", "CARD")


class CustomerPayment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "customer_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("status IN ('POSTED', 'VOIDED')", name="status_valid"),
        CheckConstraint(
            "method IN ('CASH', 'BANK_TRANSFER', 'MOBILE_MONEY', 'CHEQUE', 'CARD')",
            name="method_valid",
        ),
    )

    receipt_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("customers.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sales_invoices.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default=PaymentStatus.POSTED)
    received_by_id: Mapped[uuid.UUID | None] = mapped_column(
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

    invoice: Mapped[SalesInvoice] = relationship(back_populates="payments")
    customer: Mapped[Customer] = relationship(lazy="joined")

    @property
    def invoice_number(self) -> str | None:
        return self.invoice.invoice_number if self.invoice else None
