"""Expenses, supplier bills and payments, receivables/payables aging and customer statements."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.auth.permissions import Perm
from app.config import get_settings
from app.models.finance import (
    BillStatus,
    Expense,
    ExpenseCategory,
    ExpenseStatus,
    SupplierBill,
    SupplierPayment,
)
from app.models.organization import Branch
from app.models.partners import Customer, Supplier
from app.models.procurement import POStatus, PurchaseOrder
from app.models.sales import CustomerPayment, InvoiceStatus, PaymentStatus, SalesInvoice
from app.repositories.query import get_for_update_or_404, get_or_404, paginate, search_clause
from app.schemas.common import Page, PageParams
from app.schemas.finance import (
    BillCreate,
    ExpenseCreate,
    ExpenseUpdate,
    SupplierPaymentCreate,
)
from app.services.audit import AuditService, diff, snapshot
from app.services.base import require_active, require_exists
from app.services.master_data import MasterDataService
from app.services.notifications import NotificationService
from app.utils.exceptions import BusinessRuleError, ConflictError
from app.utils.money import ZERO, money
from app.utils.sequences import next_number
from app.utils.time import local_today, utcnow

_EXPENSE_FIELDS = (
    "category_id",
    "branch_id",
    "expense_date",
    "payee",
    "description",
    "amount",
    "tax_amount",
    "method",
    "reference",
)


class ExpenseCategoryService(MasterDataService):
    model = ExpenseCategory
    label = "Expense category"
    entity_type = "expense_category"
    action_prefix = "expense_categories"
    unique_fields = {"name": "category name"}
    required_fields = ("name", "is_active")
    sort_fields = {"name": ExpenseCategory.name, "created_at": ExpenseCategory.created_at}
    default_sort = ("name", "asc")
    search_columns = (ExpenseCategory.name,)
    audited_fields = ("name", "description", "is_active")


def _bucket(days_overdue: int) -> str:
    if days_overdue <= 0:
        return "current"
    if days_overdue <= 30:
        return "days_1_30"
    if days_overdue <= 60:
        return "days_31_60"
    if days_overdue <= 90:
        return "days_61_90"
    return "days_over_90"


_BUCKETS = ("current", "days_1_30", "days_31_60", "days_61_90", "days_over_90")


def _aging(documents: list[tuple[Any, date, Decimal]], as_of: date) -> dict[str, Any]:
    """documents: (party, due_date, balance). Returns rows per party plus grand totals."""
    per_party: dict[uuid.UUID, dict[str, Any]] = {}
    for party, due_date, balance in documents:
        row = per_party.setdefault(
            party.id,
            {"party": party, "documents": 0, **dict.fromkeys(_BUCKETS, ZERO)},
        )
        row[_bucket((as_of - due_date).days)] += balance
        row["documents"] += 1
    rows = []
    for row in sorted(per_party.values(), key=lambda r: r["party"].name.lower()):
        row["total"] = sum((row[b] for b in _BUCKETS), ZERO)
        rows.append(row)
    totals = {b: sum((r[b] for r in rows), ZERO) for b in _BUCKETS}
    totals["total"] = sum(totals.values(), ZERO)
    return {"as_of": as_of, "rows": rows, "totals": totals}


class FinanceService:
    EXPENSE_SORT = {
        "expense_date": Expense.expense_date,
        "amount": Expense.amount,
        "expense_number": Expense.expense_number,
        "created_at": Expense.created_at,
    }
    BILL_SORT = {
        "bill_date": SupplierBill.bill_date,
        "due_date": SupplierBill.due_date,
        "total": SupplierBill.total,
        "bill_number": SupplierBill.bill_number,
        "created_at": SupplierBill.created_at,
    }
    PAYMENT_SORT = {
        "payment_date": SupplierPayment.payment_date,
        "amount": SupplierPayment.amount,
        "payment_number": SupplierPayment.payment_number,
    }

    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.notifications = NotificationService(db)

    # ================================================================== expenses
    def list_expenses(
        self,
        params: PageParams,
        *,
        status: str | None,
        category_id: uuid.UUID | None,
        branch_id: uuid.UUID | None,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        stmt = select(Expense)
        if status:
            stmt = stmt.where(Expense.status == status)
        if category_id:
            stmt = stmt.where(Expense.category_id == category_id)
        if branch_id:
            stmt = stmt.where(Expense.branch_id == branch_id)
        if date_from:
            stmt = stmt.where(Expense.expense_date >= date_from)
        if date_to:
            stmt = stmt.where(Expense.expense_date <= date_to)
        if params.search:
            stmt = stmt.where(
                search_clause(
                    params.search, Expense.expense_number, Expense.payee, Expense.description
                )
            )
        items, total = paginate(
            self.db, stmt, params, self.EXPENSE_SORT, ("expense_date", "desc"), Expense.id
        )
        return Page.build(items, total, params).model_dump()

    def get_expense(self, expense_id: uuid.UUID) -> Expense:
        return get_or_404(self.db, Expense, expense_id, "Expense")

    def _check_expense_refs(self, values: dict[str, Any]) -> None:
        if values.get("category_id"):
            category = require_exists(
                self.db, ExpenseCategory, values["category_id"], "category_id"
            )
            require_active(category, "category_id")
        if values.get("branch_id"):
            require_active(
                require_exists(self.db, Branch, values["branch_id"], "branch_id"), "branch_id"
            )
        if values.get("expense_date") and values["expense_date"] > local_today():
            raise BusinessRuleError("expense_date cannot be in the future")

    def create_expense(self, ctx: AuthContext, data: ExpenseCreate) -> Expense:
        values = data.model_dump()
        values["expense_date"] = values["expense_date"] or local_today()
        self._check_expense_refs(values)
        expense = Expense(
            **values,
            expense_number=next_number(self.db, "EXP"),
            status=ExpenseStatus.PENDING,
            submitted_by_id=ctx.user.id,
        )
        self.db.add(expense)
        self.db.flush()
        self.audit.log(
            "finance.expense_create",
            actor=ctx.user,
            entity_type="expense",
            entity_id=expense.id,
            summary=f"{expense.expense_number}: {expense.total} to {expense.payee}",
        )
        self.notifications.notify_permission(
            Perm.FINANCE_APPROVE,
            f"Expense {expense.expense_number} awaiting approval",
            f"{ctx.user.full_name} submitted {expense.total} to {expense.payee}: "
            f"{expense.description[:120]}",
            category="APPROVAL",
            entity_type="expense",
            entity_id=expense.id,
            exclude_user_id=ctx.user.id,
        )
        self.db.commit()
        self.db.refresh(expense)
        return expense

    def update_expense(
        self, ctx: AuthContext, expense_id: uuid.UUID, data: ExpenseUpdate
    ) -> Expense:
        expense = get_for_update_or_404(self.db, Expense, expense_id, "Expense")
        if expense.status != ExpenseStatus.PENDING:
            raise BusinessRuleError("Only pending expenses can be edited")
        changes = data.model_dump(exclude_unset=True)
        for field in (
            "category_id",
            "expense_date",
            "payee",
            "description",
            "amount",
            "tax_amount",
        ):
            if field in changes and changes[field] is None:
                raise BusinessRuleError(f"{field} cannot be null")
        self._check_expense_refs(changes)
        before = snapshot(expense, _EXPENSE_FIELDS)
        for key, value in changes.items():
            setattr(expense, key, value)
        delta = diff(before, snapshot(expense, _EXPENSE_FIELDS))
        if delta:
            self.audit.log(
                "finance.expense_update",
                actor=ctx.user,
                entity_type="expense",
                entity_id=expense.id,
                changes=delta,
            )
        self.db.commit()
        self.db.refresh(expense)
        return expense

    def delete_expense(self, ctx: AuthContext, expense_id: uuid.UUID) -> None:
        expense = get_for_update_or_404(self.db, Expense, expense_id, "Expense")
        if expense.status != ExpenseStatus.PENDING:
            raise BusinessRuleError("Only pending expenses can be deleted")
        self.audit.log(
            "finance.expense_delete",
            actor=ctx.user,
            entity_type="expense",
            entity_id=expense.id,
            summary=f"Deleted {expense.expense_number}",
        )
        self.db.delete(expense)
        self.db.commit()

    def review_expense(
        self, ctx: AuthContext, expense_id: uuid.UUID, approve: bool, comment: str | None
    ) -> Expense:
        expense = get_for_update_or_404(self.db, Expense, expense_id, "Expense")
        if expense.status != ExpenseStatus.PENDING:
            raise BusinessRuleError(f"This expense has already been {expense.status.lower()}")
        if expense.submitted_by_id == ctx.user.id:
            raise BusinessRuleError("You cannot approve or reject an expense you submitted")
        expense.status = ExpenseStatus.APPROVED if approve else ExpenseStatus.REJECTED
        expense.reviewed_by_id = ctx.user.id
        expense.reviewed_at = utcnow()
        expense.review_comment = comment
        verb = "approved" if approve else "rejected"
        self.audit.log(
            "finance.expense_approve" if approve else "finance.expense_reject",
            actor=ctx.user,
            entity_type="expense",
            entity_id=expense.id,
            summary=f"{expense.expense_number} {verb}",
            changes={"status": {"from": "PENDING", "to": expense.status}, "comment": comment},
        )
        if expense.submitted_by_id:
            self.notifications.notify(
                [expense.submitted_by_id],
                f"Expense {expense.expense_number} {verb}",
                f"Your expense of {expense.total} to {expense.payee} was {verb}."
                + (f" Comment: {comment}" if comment else ""),
                category="SUCCESS" if approve else "INFO",
                entity_type="expense",
                entity_id=expense.id,
            )
        self.db.commit()
        self.db.refresh(expense)
        return expense

    # ================================================================== supplier bills
    def list_bills(
        self,
        params: PageParams,
        *,
        status: str | None,
        supplier_id: uuid.UUID | None,
        overdue: bool | None,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        stmt = select(SupplierBill).join(Supplier, Supplier.id == SupplierBill.supplier_id)
        if status:
            stmt = stmt.where(SupplierBill.status == status)
        if supplier_id:
            stmt = stmt.where(SupplierBill.supplier_id == supplier_id)
        if overdue is not None:
            is_overdue = SupplierBill.status.in_(BillStatus.OPEN) & (
                SupplierBill.due_date < local_today()
            )
            stmt = stmt.where(is_overdue if overdue else ~is_overdue)
        if date_from:
            stmt = stmt.where(SupplierBill.bill_date >= date_from)
        if date_to:
            stmt = stmt.where(SupplierBill.bill_date <= date_to)
        if params.search:
            stmt = stmt.where(
                search_clause(
                    params.search,
                    SupplierBill.bill_number,
                    SupplierBill.supplier_invoice_number,
                    Supplier.name,
                )
            )
        items, total = paginate(
            self.db, stmt, params, self.BILL_SORT, ("due_date", "asc"), SupplierBill.id
        )
        return Page.build(items, total, params).model_dump()

    def get_bill(self, bill_id: uuid.UUID) -> SupplierBill:
        return get_or_404(self.db, SupplierBill, bill_id, "Supplier bill")

    def create_bill(self, ctx: AuthContext, data: BillCreate) -> SupplierBill:
        supplier = require_exists(self.db, Supplier, data.supplier_id, "supplier_id")
        require_active(supplier, "supplier_id")
        total = money(data.subtotal + data.tax_total)
        duplicate = self.db.scalar(
            select(SupplierBill.id).where(
                SupplierBill.supplier_id == supplier.id,
                SupplierBill.supplier_invoice_number == data.supplier_invoice_number,
            )
        )
        if duplicate:
            raise ConflictError(
                "This supplier invoice has already been entered",
                errors=[{"field": "supplier_invoice_number", "message": "Already entered"}],
            )
        if data.purchase_order_id:
            order = require_exists(
                self.db, PurchaseOrder, data.purchase_order_id, "purchase_order_id"
            )
            if order.supplier_id != supplier.id:
                raise BusinessRuleError("The purchase order belongs to a different supplier")
            if order.status in (POStatus.DRAFT, POStatus.CANCELLED):
                raise BusinessRuleError("Bills can only be linked to approved purchase orders")
            already = Decimal(
                self.db.scalar(
                    select(func.coalesce(func.sum(SupplierBill.total), 0)).where(
                        SupplierBill.purchase_order_id == order.id,
                        SupplierBill.status != BillStatus.CANCELLED,
                    )
                )
                or 0
            )
            if already + total > order.total:
                raise BusinessRuleError(
                    f"Billed amount would exceed {order.po_number}: order total {order.total}, "
                    f"already billed {already}, this bill {total}"
                )
        bill_date = data.bill_date or local_today()
        bill = SupplierBill(
            bill_number=next_number(self.db, "BILL"),
            supplier_id=supplier.id,
            purchase_order_id=data.purchase_order_id,
            supplier_invoice_number=data.supplier_invoice_number,
            bill_date=bill_date,
            due_date=data.due_date or bill_date + timedelta(days=supplier.payment_terms_days),
            status=BillStatus.PENDING,
            currency=get_settings().DEFAULT_CURRENCY,
            subtotal=money(data.subtotal),
            tax_total=money(data.tax_total),
            total=total,
            amount_paid=ZERO,
            notes=data.notes,
            created_by_id=ctx.user.id,
        )
        if bill.due_date < bill.bill_date:
            raise BusinessRuleError("due_date cannot be before bill_date")
        self.db.add(bill)
        self.db.flush()
        self.audit.log(
            "finance.bill_create",
            actor=ctx.user,
            entity_type="supplier_bill",
            entity_id=bill.id,
            summary=f"{bill.bill_number} from {supplier.name} ({data.supplier_invoice_number}): "
            f"{total}",
        )
        self.notifications.notify_permission(
            Perm.FINANCE_APPROVE,
            f"Supplier bill {bill.bill_number} awaiting approval",
            f"{supplier.name} invoice {data.supplier_invoice_number} for {total}, "
            f"due {bill.due_date}.",
            category="APPROVAL",
            entity_type="supplier_bill",
            entity_id=bill.id,
            exclude_user_id=ctx.user.id,
        )
        self.db.commit()
        self.db.refresh(bill)
        return bill

    def approve_bill(self, ctx: AuthContext, bill_id: uuid.UUID) -> SupplierBill:
        bill = get_for_update_or_404(self.db, SupplierBill, bill_id, "Supplier bill")
        if bill.status != BillStatus.PENDING:
            raise BusinessRuleError(
                f"Only pending bills can be approved (this one is {bill.status})"
            )
        bill.status = BillStatus.APPROVED
        bill.approved_by_id = ctx.user.id
        bill.approved_at = utcnow()
        self.audit.log(
            "finance.bill_approve",
            actor=ctx.user,
            entity_type="supplier_bill",
            entity_id=bill.id,
            summary=f"Approved {bill.bill_number}",
        )
        self.db.commit()
        self.db.refresh(bill)
        return bill

    def cancel_bill(self, ctx: AuthContext, bill_id: uuid.UUID, reason: str) -> SupplierBill:
        bill = get_for_update_or_404(self.db, SupplierBill, bill_id, "Supplier bill")
        if bill.status not in (BillStatus.PENDING, BillStatus.APPROVED):
            raise BusinessRuleError("Only unpaid bills can be cancelled. Void the payments first.")
        previous = bill.status
        bill.status = BillStatus.CANCELLED
        bill.cancelled_by_id = ctx.user.id
        bill.cancelled_at = utcnow()
        bill.cancel_reason = reason
        self.audit.log(
            "finance.bill_cancel",
            actor=ctx.user,
            entity_type="supplier_bill",
            entity_id=bill.id,
            summary=f"Cancelled {bill.bill_number}: {reason}",
            changes={"status": {"from": previous, "to": BillStatus.CANCELLED}},
        )
        self.db.commit()
        self.db.refresh(bill)
        return bill

    @staticmethod
    def _bill_payment_status(bill: SupplierBill) -> None:
        if bill.amount_paid <= 0:
            bill.status = BillStatus.APPROVED
        elif bill.amount_paid < bill.total:
            bill.status = BillStatus.PARTIALLY_PAID
        else:
            bill.status = BillStatus.PAID

    def pay_bill(
        self, ctx: AuthContext, bill_id: uuid.UUID, data: SupplierPaymentCreate
    ) -> SupplierPayment:
        bill = get_for_update_or_404(self.db, SupplierBill, bill_id, "Supplier bill")
        if bill.status not in BillStatus.OPEN:
            raise BusinessRuleError(
                f"Only approved, unpaid bills can be paid (this one is {bill.status})"
            )
        amount = money(data.amount)
        if amount > bill.balance_due:
            raise BusinessRuleError(
                f"Payment of {amount} exceeds the balance of {bill.balance_due}"
            )
        payment_date = data.payment_date or local_today()
        if payment_date < bill.bill_date:
            raise BusinessRuleError("Payment date cannot be before the bill date")
        payment = SupplierPayment(
            payment_number=next_number(self.db, "PAY"),
            supplier_id=bill.supplier_id,
            bill_id=bill.id,
            amount=amount,
            payment_date=payment_date,
            method=data.method,
            reference=data.reference,
            notes=data.notes,
            status=PaymentStatus.POSTED,
            paid_by_id=ctx.user.id,
        )
        self.db.add(payment)
        bill.amount_paid = bill.amount_paid + amount
        self._bill_payment_status(bill)
        self.db.flush()
        self.audit.log(
            "finance.supplier_payment",
            actor=ctx.user,
            entity_type="supplier_payment",
            entity_id=payment.id,
            summary=f"{payment.payment_number}: paid {amount} on {bill.bill_number}",
        )
        self.db.commit()
        self.db.refresh(payment)
        return payment

    def void_supplier_payment(
        self, ctx: AuthContext, payment_id: uuid.UUID, reason: str
    ) -> SupplierPayment:
        payment = get_for_update_or_404(self.db, SupplierPayment, payment_id, "Payment")
        if payment.status == PaymentStatus.VOIDED:
            raise BusinessRuleError("Payment is already voided")
        bill = get_for_update_or_404(self.db, SupplierBill, payment.bill_id, "Supplier bill")
        payment.status = PaymentStatus.VOIDED
        payment.voided_by_id = ctx.user.id
        payment.voided_at = utcnow()
        payment.void_reason = reason
        bill.amount_paid = max(ZERO, bill.amount_paid - payment.amount)
        self._bill_payment_status(bill)
        self.audit.log(
            "finance.supplier_payment_void",
            actor=ctx.user,
            entity_type="supplier_payment",
            entity_id=payment.id,
            summary=f"Voided {payment.payment_number} ({payment.amount}): {reason}",
        )
        self.db.commit()
        self.db.refresh(payment)
        return payment

    def list_supplier_payments(
        self,
        params: PageParams,
        *,
        supplier_id: uuid.UUID | None,
        bill_id: uuid.UUID | None,
        status: str | None,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        stmt = select(SupplierPayment)
        if supplier_id:
            stmt = stmt.where(SupplierPayment.supplier_id == supplier_id)
        if bill_id:
            stmt = stmt.where(SupplierPayment.bill_id == bill_id)
        if status:
            stmt = stmt.where(SupplierPayment.status == status)
        if date_from:
            stmt = stmt.where(SupplierPayment.payment_date >= date_from)
        if date_to:
            stmt = stmt.where(SupplierPayment.payment_date <= date_to)
        if params.search:
            stmt = stmt.where(
                search_clause(
                    params.search, SupplierPayment.payment_number, SupplierPayment.reference
                )
            )
        items, total = paginate(
            self.db, stmt, params, self.PAYMENT_SORT, ("payment_date", "desc"), SupplierPayment.id
        )
        return Page.build(items, total, params).model_dump()

    # ================================================================== aging / statements
    def receivables_aging(self) -> dict[str, Any]:
        invoices = self.db.scalars(
            select(SalesInvoice).where(
                SalesInvoice.status.in_(InvoiceStatus.OPEN),
                SalesInvoice.total > SalesInvoice.amount_paid,
            )
        ).all()
        return _aging(
            [(inv.customer, inv.due_date, inv.balance_due) for inv in invoices], local_today()
        )

    def payables_aging(self) -> dict[str, Any]:
        bills = self.db.scalars(
            select(SupplierBill).where(
                SupplierBill.status.in_(BillStatus.OPEN),
                SupplierBill.total > SupplierBill.amount_paid,
            )
        ).all()
        return _aging([(b.supplier, b.due_date, b.balance_due) for b in bills], local_today())

    def customer_statement(
        self, customer_id: uuid.UUID, date_from: date, date_to: date
    ) -> dict[str, Any]:
        if date_to < date_from:
            raise BusinessRuleError("date_to cannot be before date_from")
        customer = get_or_404(self.db, Customer, customer_id, "Customer")
        posted = InvoiceStatus.POSTED

        def invoiced(before: date | None = None, start: date | None = None) -> Any:
            stmt = select(SalesInvoice).where(
                SalesInvoice.customer_id == customer.id, SalesInvoice.status.in_(posted)
            )
            if before:
                stmt = stmt.where(SalesInvoice.invoice_date < before)
            if start:
                stmt = stmt.where(
                    SalesInvoice.invoice_date >= start, SalesInvoice.invoice_date <= date_to
                )
            return stmt

        def paid(before: date | None = None, start: date | None = None) -> Any:
            stmt = select(CustomerPayment).where(
                CustomerPayment.customer_id == customer.id,
                CustomerPayment.status == PaymentStatus.POSTED,
            )
            if before:
                stmt = stmt.where(CustomerPayment.payment_date < before)
            if start:
                stmt = stmt.where(
                    CustomerPayment.payment_date >= start, CustomerPayment.payment_date <= date_to
                )
            return stmt

        opening = sum((i.total for i in self.db.scalars(invoiced(before=date_from))), ZERO) - sum(
            (p.amount for p in self.db.scalars(paid(before=date_from))), ZERO
        )
        entries: list[dict[str, Any]] = []
        for inv in self.db.scalars(invoiced(start=date_from)):
            entries.append(
                {
                    "date": inv.invoice_date,
                    "type": "INVOICE",
                    "reference": inv.invoice_number or "",
                    "description": f"Invoice due {inv.due_date}",
                    "debit": inv.total,
                    "credit": ZERO,
                }
            )
        for pay in self.db.scalars(paid(start=date_from)):
            entries.append(
                {
                    "date": pay.payment_date,
                    "type": "PAYMENT",
                    "reference": pay.receipt_number,
                    "description": f"Payment ({pay.method.replace('_', ' ').lower()})",
                    "debit": ZERO,
                    "credit": pay.amount,
                }
            )
        entries.sort(key=lambda e: (e["date"], e["type"] != "INVOICE", e["reference"]))
        balance = opening
        for entry in entries:
            balance = balance + entry["debit"] - entry["credit"]
            entry["balance"] = balance
        return {
            "customer": customer,
            "date_from": date_from,
            "date_to": date_to,
            "opening_balance": opening,
            "lines": entries,
            "closing_balance": balance,
        }
