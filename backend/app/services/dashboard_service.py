"""Dashboard: key figures, each section shown only if the user may see that module."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.auth.permissions import Perm
from app.config import get_settings
from app.models.assets import Asset
from app.models.finance import BillStatus, Expense, ExpenseStatus, SupplierBill
from app.models.hr import Employee, EmployeeStatus, LeaveRequest, LeaveStatus
from app.models.inventory import StockLevel
from app.models.partners import Product
from app.models.procurement import POStatus, PurchaseOrder
from app.models.sales import CustomerPayment, InvoiceStatus, PaymentStatus, SalesInvoice
from app.schemas.common import PageParams
from app.services.inventory_service import InventoryService
from app.services.notifications import NotificationService
from app.utils.money import ZERO, money
from app.utils.time import local_today


def _month_bounds(today: date) -> tuple[date, date]:
    start = today.replace(day=1)
    next_month = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return start, next_month


def _months_back(today: date, count: int) -> list[date]:
    months = []
    year, month = today.year, today.month
    for _ in range(count):
        months.append(date(year, month, 1))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(months))


class DashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _scalar(self, stmt: Any) -> Any:
        return self.db.scalar(stmt) or 0

    def summary(self, ctx: AuthContext) -> dict[str, Any]:
        today = local_today()
        month_start, next_month = _month_bounds(today)
        data: dict[str, Any] = {
            "as_of": today,
            "currency": get_settings().DEFAULT_CURRENCY,
            "unread_notifications": NotificationService(self.db).unread_count(ctx.user.id),
            "pending_approvals": {},
        }
        approvals = data["pending_approvals"]

        if ctx.has(Perm.SALES_VIEW):
            in_month = (
                SalesInvoice.status.in_(InvoiceStatus.POSTED),
                SalesInvoice.invoice_date >= month_start,
                SalesInvoice.invoice_date < next_month,
            )
            overdue = (
                SalesInvoice.status.in_(InvoiceStatus.OPEN),
                SalesInvoice.due_date < today,
            )
            trend_start = _months_back(today, 6)[0]
            # One expression object, so SELECT and GROUP BY share the same bind parameter.
            month_expr = func.to_char(SalesInvoice.invoice_date, "YYYY-MM")
            trend_rows = dict(
                self.db.execute(
                    select(month_expr, func.sum(SalesInvoice.subtotal))
                    .where(
                        SalesInvoice.status.in_(InvoiceStatus.POSTED),
                        SalesInvoice.invoice_date >= trend_start,
                    )
                    .group_by(month_expr)
                ).all()
            )
            data["sales"] = {
                "invoiced_this_month": money(
                    self._scalar(select(func.sum(SalesInvoice.total)).where(*in_month))
                ),
                "invoices_this_month": self._scalar(
                    select(func.count(SalesInvoice.id)).where(*in_month)
                ),
                "collected_this_month": money(
                    self._scalar(
                        select(func.sum(CustomerPayment.amount)).where(
                            CustomerPayment.status == PaymentStatus.POSTED,
                            CustomerPayment.payment_date >= month_start,
                            CustomerPayment.payment_date < next_month,
                        )
                    )
                ),
                "overdue_invoices": self._scalar(
                    select(func.count(SalesInvoice.id)).where(*overdue)
                ),
                "overdue_amount": money(
                    self._scalar(
                        select(func.sum(SalesInvoice.total - SalesInvoice.amount_paid)).where(
                            *overdue
                        )
                    )
                ),
                "monthly_net_sales": [
                    {
                        "month": m.strftime("%Y-%m"),
                        "net_sales": money(trend_rows.get(m.strftime("%Y-%m"), 0)),
                    }
                    for m in _months_back(today, 6)
                ],
            }
        if ctx.has(Perm.SALES_APPROVE):
            approvals["sales_invoices"] = self._scalar(
                select(func.count(SalesInvoice.id)).where(
                    SalesInvoice.status == InvoiceStatus.DRAFT
                )
            )

        if ctx.has(Perm.FINANCE_VIEW):
            data["finance"] = {
                "receivables_outstanding": money(
                    self._scalar(
                        select(func.sum(SalesInvoice.total - SalesInvoice.amount_paid)).where(
                            SalesInvoice.status.in_(InvoiceStatus.OPEN)
                        )
                    )
                ),
                "payables_outstanding": money(
                    self._scalar(
                        select(func.sum(SupplierBill.total - SupplierBill.amount_paid)).where(
                            SupplierBill.status.in_(BillStatus.OPEN)
                        )
                    )
                ),
                "expenses_this_month": money(
                    self._scalar(
                        select(func.sum(Expense.amount + Expense.tax_amount)).where(
                            Expense.status == ExpenseStatus.APPROVED,
                            Expense.expense_date >= month_start,
                            Expense.expense_date < next_month,
                        )
                    )
                ),
                "bills_due_in_7_days": self._scalar(
                    select(func.count(SupplierBill.id)).where(
                        SupplierBill.status.in_(BillStatus.OPEN),
                        SupplierBill.due_date >= today,
                        SupplierBill.due_date <= date.fromordinal(today.toordinal() + 7),
                    )
                ),
            }
        if ctx.has(Perm.FINANCE_APPROVE):
            approvals["expenses"] = self._scalar(
                select(func.count(Expense.id)).where(Expense.status == ExpenseStatus.PENDING)
            )
            approvals["supplier_bills"] = self._scalar(
                select(func.count(SupplierBill.id)).where(SupplierBill.status == BillStatus.PENDING)
            )

        if ctx.has(Perm.INVENTORY_VIEW):
            stock_value = self._scalar(
                select(func.sum(StockLevel.quantity * Product.cost_price)).join(
                    Product, Product.id == StockLevel.product_id
                )
            )
            low = InventoryService(self.db).low_stock(PageParams(page=1, page_size=1))
            data["inventory"] = {
                "stock_value": money(stock_value),
                "active_products": self._scalar(
                    select(func.count(Product.id)).where(Product.is_active.is_(True))
                ),
                "low_stock_products": low["meta"]["total"],
            }

        if ctx.has(Perm.PROCUREMENT_VIEW):
            data["procurement"] = {
                "open_purchase_orders": self._scalar(
                    select(func.count(PurchaseOrder.id)).where(
                        PurchaseOrder.status.in_(POStatus.RECEIVABLE)
                    )
                ),
                "open_order_value": money(
                    self._scalar(
                        select(func.sum(PurchaseOrder.total)).where(
                            PurchaseOrder.status.in_(POStatus.RECEIVABLE)
                        )
                    )
                ),
            }
        if ctx.has(Perm.PROCUREMENT_APPROVE):
            approvals["purchase_orders"] = self._scalar(
                select(func.count(PurchaseOrder.id)).where(PurchaseOrder.status == POStatus.DRAFT)
            )

        if ctx.has(Perm.EMPLOYEES_VIEW):
            data["hr"] = {
                "headcount": self._scalar(
                    select(func.count(Employee.id)).where(
                        Employee.status != EmployeeStatus.TERMINATED
                    )
                ),
                "on_leave_today": self._scalar(
                    select(func.count(func.distinct(LeaveRequest.employee_id))).where(
                        LeaveRequest.status == LeaveStatus.APPROVED,
                        LeaveRequest.start_date <= today,
                        LeaveRequest.end_date >= today,
                    )
                ),
            }
        if ctx.has(Perm.LEAVE_APPROVE):
            approvals["leave_requests"] = self._scalar(
                select(func.count(LeaveRequest.id)).where(
                    LeaveRequest.status == LeaveStatus.PENDING
                )
            )

        if ctx.has(Perm.ASSETS_VIEW):
            active = self.db.scalars(select(Asset).where(Asset.status != "DISPOSED")).all()
            data["assets"] = {
                "active_assets": len(active),
                "total_cost": money(sum((a.purchase_cost for a in active), ZERO)),
                "total_book_value": money(sum((a.book_value for a in active), Decimal(0))),
            }
        return data
