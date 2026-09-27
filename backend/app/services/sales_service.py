"""Sales invoices: drafts, issuing (stock + credit checks), cancellation and customer payments."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.config import get_settings
from app.models.inventory import MovementType, Warehouse
from app.models.organization import Branch
from app.models.partners import Customer, Product
from app.models.sales import (
    CustomerPayment,
    InvoiceStatus,
    PaymentStatus,
    SalesInvoice,
    SalesInvoiceLine,
)
from app.repositories.query import get_for_update_or_404, get_or_404, paginate, search_clause
from app.schemas.common import Page, PageParams
from app.schemas.sales import InvoiceCreate, InvoiceLineIn, InvoiceUpdate, PaymentCreate
from app.services.audit import AuditService
from app.services.base import require_active, require_exists
from app.services.inventory_service import InventoryService
from app.services.pricing import document_totals, line_amounts
from app.utils.exceptions import BusinessRuleError
from app.utils.money import ZERO, money
from app.utils.sequences import next_number
from app.utils.time import local_today, utcnow


def recalculate_payment_status(invoice: SalesInvoice) -> None:
    if invoice.status in (InvoiceStatus.DRAFT, InvoiceStatus.CANCELLED):
        return
    if invoice.amount_paid <= 0:
        invoice.status = InvoiceStatus.ISSUED
    elif invoice.amount_paid < invoice.total:
        invoice.status = InvoiceStatus.PARTIALLY_PAID
    else:
        invoice.status = InvoiceStatus.PAID


class SalesService:
    INVOICE_SORT = {
        "invoice_date": SalesInvoice.invoice_date,
        "due_date": SalesInvoice.due_date,
        "invoice_number": SalesInvoice.invoice_number,
        "total": SalesInvoice.total,
        "created_at": SalesInvoice.created_at,
    }
    PAYMENT_SORT = {
        "payment_date": CustomerPayment.payment_date,
        "amount": CustomerPayment.amount,
        "receipt_number": CustomerPayment.receipt_number,
    }

    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.inventory = InventoryService(db)

    # ================================================================== queries
    def list_invoices(
        self,
        params: PageParams,
        *,
        status: str | None,
        customer_id: uuid.UUID | None,
        date_from: date | None,
        date_to: date | None,
        overdue: bool | None,
    ) -> dict[str, Any]:
        stmt = select(SalesInvoice).join(Customer, Customer.id == SalesInvoice.customer_id)
        if status:
            stmt = stmt.where(SalesInvoice.status == status)
        if customer_id:
            stmt = stmt.where(SalesInvoice.customer_id == customer_id)
        if date_from:
            stmt = stmt.where(SalesInvoice.invoice_date >= date_from)
        if date_to:
            stmt = stmt.where(SalesInvoice.invoice_date <= date_to)
        if overdue is not None:
            is_overdue = SalesInvoice.status.in_(InvoiceStatus.OPEN) & (
                SalesInvoice.due_date < local_today()
            )
            stmt = stmt.where(is_overdue if overdue else ~is_overdue)
        if params.search:
            stmt = stmt.where(
                search_clause(
                    params.search,
                    SalesInvoice.invoice_number,
                    SalesInvoice.customer_reference,
                    Customer.name,
                    Customer.code,
                )
            )
        items, total = paginate(
            self.db, stmt, params, self.INVOICE_SORT, ("created_at", "desc"), SalesInvoice.id
        )
        return Page.build(items, total, params).model_dump()

    def get_invoice(self, invoice_id: uuid.UUID) -> SalesInvoice:
        return get_or_404(self.db, SalesInvoice, invoice_id, "Invoice")

    def _lock(self, invoice_id: uuid.UUID) -> SalesInvoice:
        return get_for_update_or_404(self.db, SalesInvoice, invoice_id, "Invoice")

    # ================================================================== drafts
    def _customer(self, customer_id: uuid.UUID) -> Customer:
        customer = require_exists(self.db, Customer, customer_id, "customer_id")
        require_active(customer, "customer_id")
        return customer

    def _check_refs(self, values: dict[str, Any]) -> None:
        if values.get("branch_id"):
            require_active(
                require_exists(self.db, Branch, values["branch_id"], "branch_id"), "branch_id"
            )
        if values.get("warehouse_id"):
            require_active(
                require_exists(self.db, Warehouse, values["warehouse_id"], "warehouse_id"),
                "warehouse_id",
            )

    def _build_lines(self, invoice: SalesInvoice, lines: list[InvoiceLineIn]) -> None:
        invoice.lines.clear()
        self.db.flush()
        amounts = []
        for number, line in enumerate(lines, start=1):
            product = require_exists(
                self.db, Product, line.product_id, f"lines.{number - 1}.product_id"
            )
            require_active(product, f"lines.{number - 1}.product_id")
            unit_price = line.unit_price if line.unit_price is not None else product.selling_price
            tax_rate = line.tax_rate if line.tax_rate is not None else product.tax_rate
            calc = line_amounts(line.quantity, unit_price, line.discount_percent, tax_rate)
            amounts.append(calc)
            invoice.lines.append(
                SalesInvoiceLine(
                    line_no=number,
                    product_id=product.id,
                    description=line.description or product.name,
                    quantity=line.quantity,
                    unit_price=money(unit_price),
                    discount_percent=line.discount_percent,
                    tax_rate=tax_rate,
                    discount_amount=calc.discount_amount,
                    line_subtotal=calc.subtotal,
                    line_tax=calc.tax,
                    line_total=calc.total,
                )
            )
        totals = document_totals(amounts)
        invoice.subtotal = totals.subtotal
        invoice.discount_total = totals.discount_total
        invoice.tax_total = totals.tax_total
        invoice.total = totals.total

    def create_invoice(self, ctx: AuthContext, data: InvoiceCreate) -> SalesInvoice:
        customer = self._customer(data.customer_id)
        values = data.model_dump(exclude={"lines"})
        self._check_refs(values)
        invoice_date = data.invoice_date or local_today()
        invoice = SalesInvoice(
            **{**values, "invoice_date": invoice_date},
            status=InvoiceStatus.DRAFT,
            currency=self._currency(),
            created_by_id=ctx.user.id,
        )
        invoice.due_date = data.due_date or invoice_date + timedelta(
            days=customer.payment_terms_days
        )
        self.db.add(invoice)
        self._build_lines(invoice, data.lines)
        self.db.flush()
        self.audit.log(
            "sales.invoice_create",
            actor=ctx.user,
            entity_type="sales_invoice",
            entity_id=invoice.id,
            summary=f"Draft invoice for {customer.name}: {invoice.total} {invoice.currency}",
        )
        self.db.commit()
        self.db.refresh(invoice)
        return invoice

    @staticmethod
    def _currency() -> str:
        return get_settings().DEFAULT_CURRENCY

    def update_invoice(
        self, ctx: AuthContext, invoice_id: uuid.UUID, data: InvoiceUpdate
    ) -> SalesInvoice:
        invoice = self._lock(invoice_id)
        if invoice.status != InvoiceStatus.DRAFT:
            raise BusinessRuleError("Only draft invoices can be edited")
        changes = data.model_dump(exclude_unset=True, exclude={"lines"})
        if changes.get("customer_id"):
            self._customer(changes["customer_id"])
        self._check_refs(changes)
        for field in ("customer_id", "invoice_date", "due_date"):
            if field in changes and changes[field] is None:
                raise BusinessRuleError(f"{field} cannot be null")
        for key, value in changes.items():
            setattr(invoice, key, value)
        if invoice.due_date < invoice.invoice_date:
            raise BusinessRuleError("due_date cannot be before invoice_date")
        if data.lines is not None:
            self._build_lines(invoice, data.lines)
        self.audit.log(
            "sales.invoice_update",
            actor=ctx.user,
            entity_type="sales_invoice",
            entity_id=invoice.id,
            summary=f"Draft invoice updated: total {invoice.total}",
        )
        self.db.commit()
        self.db.refresh(invoice)
        return invoice

    def delete_draft(self, ctx: AuthContext, invoice_id: uuid.UUID) -> None:
        invoice = self._lock(invoice_id)
        if invoice.status != InvoiceStatus.DRAFT:
            raise BusinessRuleError("Only drafts can be deleted. Cancel an issued invoice instead.")
        self.audit.log(
            "sales.invoice_delete",
            actor=ctx.user,
            entity_type="sales_invoice",
            entity_id=invoice.id,
            summary=f"Deleted draft invoice for {invoice.customer.name}",
        )
        self.db.delete(invoice)
        self.db.commit()

    # ================================================================== issue / cancel
    def outstanding_balance(self, customer_id: uuid.UUID) -> Decimal:
        return Decimal(
            self.db.scalar(
                select(
                    func.coalesce(func.sum(SalesInvoice.total - SalesInvoice.amount_paid), 0)
                ).where(
                    SalesInvoice.customer_id == customer_id,
                    SalesInvoice.status.in_(InvoiceStatus.OPEN),
                )
            )
            or 0
        )

    def approve_invoice(self, ctx: AuthContext, invoice_id: uuid.UUID) -> SalesInvoice:
        invoice = self._lock(invoice_id)
        if invoice.status != InvoiceStatus.DRAFT:
            raise BusinessRuleError(f"Only drafts can be issued (this invoice is {invoice.status})")
        customer = self._customer(invoice.customer_id)
        if invoice.total <= 0:
            raise BusinessRuleError("An invoice must have a total greater than zero")

        if customer.credit_limit is not None:
            exposure = self.outstanding_balance(customer.id) + invoice.total
            if exposure > customer.credit_limit:
                raise BusinessRuleError(
                    f"Credit limit exceeded for {customer.name}: limit {customer.credit_limit}, "
                    f"outstanding plus this invoice {exposure}"
                )

        goods = [line for line in invoice.lines if line.product.is_stocked]
        if goods and not invoice.warehouse_id:
            raise BusinessRuleError("Choose the warehouse the goods are issued from")
        if goods:
            require_active(self.db.get(Warehouse, invoice.warehouse_id), "warehouse_id")

        invoice.invoice_number = next_number(self.db, "INV")
        for line in invoice.lines:
            line.unit_cost = line.product.cost_price
            if line.product.is_stocked:
                self.inventory.change_stock(
                    product=line.product,
                    warehouse_id=invoice.warehouse_id,
                    quantity=-line.quantity,
                    movement_type=MovementType.SALE,
                    actor=ctx.user,
                    unit_cost=line.product.cost_price,
                    reference_type="SALES_INVOICE",
                    reference_id=invoice.id,
                    reference_number=invoice.invoice_number,
                )
        invoice.status = InvoiceStatus.ISSUED
        invoice.approved_by_id = ctx.user.id
        invoice.approved_at = utcnow()
        self.audit.log(
            "sales.invoice_issue",
            actor=ctx.user,
            entity_type="sales_invoice",
            entity_id=invoice.id,
            summary=f"Issued {invoice.invoice_number} to {customer.name} for {invoice.total}",
        )
        self.db.commit()
        self.db.refresh(invoice)
        return invoice

    def cancel_invoice(self, ctx: AuthContext, invoice_id: uuid.UUID, reason: str) -> SalesInvoice:
        invoice = self._lock(invoice_id)
        if invoice.status == InvoiceStatus.DRAFT:
            raise BusinessRuleError("Drafts are deleted, not cancelled")
        if invoice.status == InvoiceStatus.CANCELLED:
            raise BusinessRuleError("Invoice is already cancelled")
        if invoice.amount_paid > 0:
            raise BusinessRuleError("Void the payments on this invoice before cancelling it")

        for line in invoice.lines:
            if line.product.is_stocked and invoice.warehouse_id:
                self.inventory.change_stock(
                    product=line.product,
                    warehouse_id=invoice.warehouse_id,
                    quantity=line.quantity,
                    movement_type=MovementType.SALE_REVERSAL,
                    actor=ctx.user,
                    unit_cost=line.unit_cost,
                    reference_type="SALES_INVOICE",
                    reference_id=invoice.id,
                    reference_number=invoice.invoice_number,
                    notes=f"Cancelled: {reason}",
                )
        previous = invoice.status
        invoice.status = InvoiceStatus.CANCELLED
        invoice.cancelled_by_id = ctx.user.id
        invoice.cancelled_at = utcnow()
        invoice.cancel_reason = reason
        self.audit.log(
            "sales.invoice_cancel",
            actor=ctx.user,
            entity_type="sales_invoice",
            entity_id=invoice.id,
            summary=f"Cancelled {invoice.invoice_number}: {reason}",
            changes={"status": {"from": previous, "to": InvoiceStatus.CANCELLED}},
        )
        self.db.commit()
        self.db.refresh(invoice)
        return invoice

    # ================================================================== payments
    def list_payments(
        self,
        params: PageParams,
        *,
        customer_id: uuid.UUID | None,
        invoice_id: uuid.UUID | None,
        method: str | None,
        status: str | None,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        stmt = select(CustomerPayment).join(Customer, Customer.id == CustomerPayment.customer_id)
        if customer_id:
            stmt = stmt.where(CustomerPayment.customer_id == customer_id)
        if invoice_id:
            stmt = stmt.where(CustomerPayment.invoice_id == invoice_id)
        if method:
            stmt = stmt.where(CustomerPayment.method == method)
        if status:
            stmt = stmt.where(CustomerPayment.status == status)
        if date_from:
            stmt = stmt.where(CustomerPayment.payment_date >= date_from)
        if date_to:
            stmt = stmt.where(CustomerPayment.payment_date <= date_to)
        if params.search:
            stmt = stmt.where(
                search_clause(
                    params.search,
                    CustomerPayment.receipt_number,
                    CustomerPayment.reference,
                    Customer.name,
                )
            )
        items, total = paginate(
            self.db, stmt, params, self.PAYMENT_SORT, ("payment_date", "desc"), CustomerPayment.id
        )
        return Page.build(items, total, params).model_dump()

    def record_payment(
        self, ctx: AuthContext, invoice_id: uuid.UUID, data: PaymentCreate
    ) -> CustomerPayment:
        invoice = self._lock(invoice_id)
        if invoice.status not in InvoiceStatus.OPEN:
            raise BusinessRuleError(
                f"Payments can only be recorded against issued, unpaid invoices "
                f"(this invoice is {invoice.status})"
            )
        amount = money(data.amount)
        if amount > invoice.balance_due:
            raise BusinessRuleError(
                f"Payment of {amount} exceeds the balance due of {invoice.balance_due}"
            )
        payment_date = data.payment_date or local_today()
        if payment_date < invoice.invoice_date:
            raise BusinessRuleError("Payment date cannot be before the invoice date")
        payment = CustomerPayment(
            receipt_number=next_number(self.db, "RCT"),
            customer_id=invoice.customer_id,
            invoice_id=invoice.id,
            amount=amount,
            payment_date=payment_date,
            method=data.method,
            reference=data.reference,
            notes=data.notes,
            status=PaymentStatus.POSTED,
            received_by_id=ctx.user.id,
        )
        self.db.add(payment)
        invoice.amount_paid = invoice.amount_paid + amount
        recalculate_payment_status(invoice)
        self.db.flush()
        self.audit.log(
            "sales.payment_record",
            actor=ctx.user,
            entity_type="customer_payment",
            entity_id=payment.id,
            summary=f"{payment.receipt_number}: {amount} by {data.method} "
            f"against {invoice.invoice_number}",
        )
        self.db.commit()
        self.db.refresh(payment)
        return payment

    def void_payment(self, ctx: AuthContext, payment_id: uuid.UUID, reason: str) -> CustomerPayment:
        payment = get_for_update_or_404(self.db, CustomerPayment, payment_id, "Payment")
        if payment.status == PaymentStatus.VOIDED:
            raise BusinessRuleError("Payment is already voided")
        invoice = self._lock(payment.invoice_id)
        payment.status = PaymentStatus.VOIDED
        payment.voided_by_id = ctx.user.id
        payment.voided_at = utcnow()
        payment.void_reason = reason
        invoice.amount_paid = max(ZERO, invoice.amount_paid - payment.amount)
        recalculate_payment_status(invoice)
        self.audit.log(
            "sales.payment_void",
            actor=ctx.user,
            entity_type="customer_payment",
            entity_id=payment.id,
            summary=f"Voided {payment.receipt_number} ({payment.amount}): {reason}",
        )
        self.db.commit()
        self.db.refresh(payment)
        return payment
