"""Dashboard and report schemas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class MonthlySales(BaseModel):
    month: str
    net_sales: Decimal


class SalesTiles(BaseModel):
    invoiced_this_month: Decimal
    invoices_this_month: int
    collected_this_month: Decimal
    overdue_invoices: int
    overdue_amount: Decimal
    monthly_net_sales: list[MonthlySales]


class FinanceTiles(BaseModel):
    receivables_outstanding: Decimal
    payables_outstanding: Decimal
    expenses_this_month: Decimal
    bills_due_in_7_days: int


class InventoryTiles(BaseModel):
    stock_value: Decimal
    active_products: int
    low_stock_products: int


class ProcurementTiles(BaseModel):
    open_purchase_orders: int
    open_order_value: Decimal


class HRTiles(BaseModel):
    headcount: int
    on_leave_today: int


class AssetTiles(BaseModel):
    active_assets: int
    total_cost: Decimal
    total_book_value: Decimal


class DashboardOut(BaseModel):
    """Sections are present only when the user holds the matching view permission."""

    as_of: date
    currency: str
    unread_notifications: int
    pending_approvals: dict[str, int]
    sales: SalesTiles | None = None
    finance: FinanceTiles | None = None
    inventory: InventoryTiles | None = None
    procurement: ProcurementTiles | None = None
    hr: HRTiles | None = None
    assets: AssetTiles | None = None


class ReportInfo(BaseModel):
    key: str
    title: str
    description: str
    uses_dates: bool
    group_by_options: list[str]


class ReportColumn(BaseModel):
    key: str
    label: str
    kind: str


class ReportOut(BaseModel):
    key: str
    title: str
    columns: list[ReportColumn]
    rows: list[dict[str, Any]]
    totals: dict[str, Any] | None
    parameters: dict[str, Any]
