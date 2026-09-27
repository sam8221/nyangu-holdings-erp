"""Customers, suppliers, product categories and products."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class _Party:
    """Columns shared by customers and suppliers."""

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    tpin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_person: Mapped[str | None] = mapped_column(String(150), nullable=True)
    payment_terms_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, _Party, Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("customer_type IN ('INDIVIDUAL', 'BUSINESS')", name="type_valid"),
        CheckConstraint("credit_limit IS NULL OR credit_limit >= 0", name="credit_limit_valid"),
        CheckConstraint("payment_terms_days >= 0", name="terms_valid"),
    )

    customer_type: Mapped[str] = mapped_column(String(20), nullable=False, default="BUSINESS")
    # NULL means no limit.
    credit_limit: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)


class Supplier(UUIDPrimaryKeyMixin, TimestampMixin, _Party, Base):
    __tablename__ = "suppliers"
    __table_args__ = (CheckConstraint("payment_terms_days >= 0", name="terms_valid"),)

    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bank_branch: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(String(50), nullable=True)


class ProductCategory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product_categories"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Product(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("product_type IN ('GOODS', 'SERVICE')", name="type_valid"),
        CheckConstraint("cost_price >= 0 AND selling_price >= 0", name="prices_non_negative"),
        CheckConstraint("tax_rate >= 0 AND tax_rate <= 100", name="tax_rate_valid"),
        CheckConstraint("reorder_level >= 0", name="reorder_level_valid"),
        CheckConstraint("sku = upper(sku)", name="sku_uppercase"),
    )

    sku: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("product_categories.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    product_type: Mapped[str] = mapped_column(String(10), nullable=False, default="GOODS")
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="pcs")
    barcode: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    # Weighted average cost, updated when goods are received.
    cost_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    selling_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=16)
    reorder_level: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    category: Mapped[ProductCategory | None] = relationship(lazy="joined")

    @property
    def is_stocked(self) -> bool:
        return self.product_type == "GOODS"
