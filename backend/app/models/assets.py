"""Fixed assets and their categories, with straight-line depreciation."""

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
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.hr import Employee
from app.models.organization import Branch
from app.utils.money import ZERO, money
from app.utils.time import local_today

DEPRECIATION_METHODS = ("STRAIGHT_LINE", "NONE")
ASSET_STATUSES = ("IN_USE", "IN_STORE", "UNDER_MAINTENANCE", "DISPOSED")


def months_between(start: date, end: date) -> int:
    """Whole months from start to end (0 if end is earlier)."""
    if end < start:
        return 0
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(months, 0)


class AssetCategory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "asset_categories"
    __table_args__ = (
        CheckConstraint("depreciation_method IN ('STRAIGHT_LINE', 'NONE')", name="method_valid"),
        CheckConstraint("useful_life_months > 0", name="life_positive"),
    )

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    depreciation_method: Mapped[str] = mapped_column(
        String(20), nullable=False, default="STRAIGHT_LINE"
    )
    useful_life_months: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Asset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('IN_USE', 'IN_STORE', 'UNDER_MAINTENANCE', 'DISPOSED')",
            name="status_valid",
        ),
        CheckConstraint("depreciation_method IN ('STRAIGHT_LINE', 'NONE')", name="method_valid"),
        CheckConstraint("purchase_cost >= 0", name="cost_non_negative"),
        CheckConstraint(
            "salvage_value >= 0 AND salvage_value <= purchase_cost", name="salvage_valid"
        ),
        CheckConstraint("useful_life_months > 0", name="life_positive"),
        CheckConstraint(
            "disposal_date IS NULL OR disposal_date >= purchase_date",
            name="disposal_after_purchase",
        ),
    )

    asset_tag: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("asset_categories.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True
    )
    assigned_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("employees.id", ondelete="SET NULL"), index=True, nullable=True
    )
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=True
    )
    serial_number: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    purchase_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    salvage_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    depreciation_method: Mapped[str] = mapped_column(String(20), nullable=False)
    useful_life_months: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False, default="IN_USE")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    disposal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    disposal_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    disposal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    disposed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    disposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    category: Mapped[AssetCategory] = relationship(lazy="joined")
    branch: Mapped[Branch | None] = relationship(lazy="joined")
    assigned_employee: Mapped[Employee | None] = relationship(lazy="joined")

    # ------------------------------------------------------------------ depreciation
    @property
    def monthly_depreciation(self) -> Decimal:
        if self.depreciation_method != "STRAIGHT_LINE":
            return ZERO
        return (self.purchase_cost - self.salvage_value) / Decimal(self.useful_life_months)

    def accumulated_depreciation_at(self, as_of: date) -> Decimal:
        if self.depreciation_method != "STRAIGHT_LINE":
            return ZERO
        end = min(as_of, self.disposal_date) if self.disposal_date else as_of
        months = min(months_between(self.purchase_date, end), self.useful_life_months)
        return money(self.monthly_depreciation * months)

    def book_value_at(self, as_of: date) -> Decimal:
        return self.purchase_cost - self.accumulated_depreciation_at(as_of)

    @property
    def accumulated_depreciation(self) -> Decimal:
        return self.accumulated_depreciation_at(local_today())

    @property
    def book_value(self) -> Decimal:
        return self.book_value_at(local_today())

    @property
    def disposal_gain_loss(self) -> Decimal | None:
        if self.disposal_date is None or self.disposal_value is None:
            return None
        return self.disposal_value - self.book_value_at(self.disposal_date)
