"""Purchase orders and goods received notes (GRNs)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
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
from app.models.partners import Product, Supplier
from app.utils.money import money


class POStatus:
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED = "RECEIVED"
    CLOSED = "CLOSED"  # short delivery accepted; nothing more expected
    CANCELLED = "CANCELLED"
    ALL = (DRAFT, APPROVED, PARTIALLY_RECEIVED, RECEIVED, CLOSED, CANCELLED)
    RECEIVABLE = (APPROVED, PARTIALLY_RECEIVED)


class PurchaseOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'APPROVED', 'PARTIALLY_RECEIVED', 'RECEIVED', 'CLOSED', "
            "'CANCELLED')",
            name="status_valid",
        ),
        CheckConstraint(
            "expected_date IS NULL OR expected_date >= order_date", name="expected_after_order"
        ),
    )

    po_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    order_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    expected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False, default="DRAFT")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="ZMW")
    supplier_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)

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
    warehouse: Mapped[Warehouse] = relationship(lazy="joined")
    lines: Mapped[list[PurchaseOrderLine]] = relationship(
        back_populates="purchase_order",
        cascade="all, delete-orphan",
        order_by="PurchaseOrderLine.line_no",
        lazy="selectin",
    )
    receipts: Mapped[list[GoodsReceipt]] = relationship(
        back_populates="purchase_order", order_by="GoodsReceipt.grn_number", lazy="selectin"
    )

    @property
    def received_value(self) -> Decimal:
        """Value (before tax) of what has been received so far."""
        return sum((money(ln.received_quantity * ln.unit_cost) for ln in self.lines), Decimal(0))


class PurchaseOrderLine(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_cost >= 0", name="cost_non_negative"),
        CheckConstraint(
            "received_quantity >= 0 AND received_quantity <= quantity", name="received_valid"
        ),
    )

    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("purchase_orders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    line_subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    line_tax: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False, default=0)

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship(lazy="joined")

    @property
    def outstanding_quantity(self) -> Decimal:
        return self.quantity - self.received_quantity


class GoodsReceipt(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "goods_receipts"

    grn_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("purchase_orders.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    received_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    delivery_note: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="receipts")
    warehouse: Mapped[Warehouse] = relationship(lazy="joined")
    lines: Mapped[list[GoodsReceiptLine]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def po_number(self) -> str:
        return self.purchase_order.po_number


class GoodsReceiptLine(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "goods_receipt_lines"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    receipt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("goods_receipts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    purchase_order_line_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    receipt: Mapped[GoodsReceipt] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship(lazy="joined")
