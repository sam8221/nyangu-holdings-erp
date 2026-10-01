"""Quotations: draft, send, accept/decline, and convert to a sales invoice."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.config import get_settings
from app.models.organization import Branch
from app.models.partners import Customer
from app.models.sales import (
    InvoiceStatus,
    Quotation,
    QuotationLine,
    QuotationStatus,
    SalesInvoice,
    SalesInvoiceLine,
)
from app.repositories.query import get_for_update_or_404, get_or_404, paginate, search_clause
from app.schemas.common import Page, PageParams
from app.schemas.sales import ConvertQuotation, QuotationCreate, QuotationUpdate
from app.services.audit import AuditService
from app.services.base import require_active, require_exists
from app.services.sales_service import (
    SalesService,
    build_document_lines,
    default_prices_include_tax,
    lines_as_input,
)
from app.services.settings_service import SettingsService
from app.utils.exceptions import BusinessRuleError
from app.utils.sequences import next_number
from app.utils.time import local_today

# Allowed manual status changes: from -> to
_TRANSITIONS = {
    QuotationStatus.DRAFT: {
        QuotationStatus.SENT,
        QuotationStatus.ACCEPTED,
        QuotationStatus.DECLINED,
    },
    QuotationStatus.SENT: {QuotationStatus.ACCEPTED, QuotationStatus.DECLINED},
    QuotationStatus.ACCEPTED: {QuotationStatus.SENT, QuotationStatus.DECLINED},
    QuotationStatus.DECLINED: {QuotationStatus.SENT},
}


class QuotationService:
    SORT = {
        "quote_date": Quotation.quote_date,
        "valid_until": Quotation.valid_until,
        "quote_number": Quotation.quote_number,
        "total": Quotation.total,
        "created_at": Quotation.created_at,
    }

    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    # ------------------------------------------------------------------ queries
    def list(
        self,
        params: PageParams,
        *,
        status: str | None,
        customer_id: uuid.UUID | None,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        stmt = select(Quotation).join(Customer, Customer.id == Quotation.customer_id)
        if status:
            stmt = stmt.where(Quotation.status == status)
        if customer_id:
            stmt = stmt.where(Quotation.customer_id == customer_id)
        if date_from:
            stmt = stmt.where(Quotation.quote_date >= date_from)
        if date_to:
            stmt = stmt.where(Quotation.quote_date <= date_to)
        if params.search:
            stmt = stmt.where(
                search_clause(
                    params.search,
                    Quotation.quote_number,
                    Quotation.customer_reference,
                    Customer.name,
                    Customer.code,
                )
            )
        items, total = paginate(
            self.db, stmt, params, self.SORT, ("created_at", "desc"), Quotation.id
        )
        return Page.build(items, total, params).model_dump()

    def get(self, quotation_id: uuid.UUID) -> Quotation:
        return get_or_404(self.db, Quotation, quotation_id, "Quotation")

    def _lock(self, quotation_id: uuid.UUID) -> Quotation:
        return get_for_update_or_404(self.db, Quotation, quotation_id, "Quotation")

    def _customer(self, customer_id: uuid.UUID) -> Customer:
        customer = require_exists(self.db, Customer, customer_id, "customer_id")
        require_active(customer, "customer_id")
        return customer

    def _check_branch(self, branch_id: uuid.UUID | None) -> None:
        if branch_id:
            require_active(require_exists(self.db, Branch, branch_id, "branch_id"), "branch_id")

    # ------------------------------------------------------------------ commands
    def create(self, ctx: AuthContext, data: QuotationCreate) -> Quotation:
        customer = self._customer(data.customer_id)
        self._check_branch(data.branch_id)
        quote_date = data.quote_date or local_today()
        validity = int(SettingsService(self.db).get("quotation_validity_days"))
        quotation = Quotation(
            quote_number=next_number(self.db, "QUO"),
            customer_id=customer.id,
            branch_id=data.branch_id,
            quote_date=quote_date,
            valid_until=data.valid_until or quote_date + timedelta(days=validity),
            status=QuotationStatus.DRAFT,
            currency=get_settings().DEFAULT_CURRENCY,
            prices_include_tax=(
                data.prices_include_tax
                if data.prices_include_tax is not None
                else default_prices_include_tax(self.db)
            ),
            customer_reference=data.customer_reference,
            notes=data.notes,
            created_by_id=ctx.user.id,
        )
        self.db.add(quotation)
        build_document_lines(self.db, quotation, data.lines, QuotationLine)
        self.db.flush()
        self.audit.log(
            "sales.quotation_create",
            actor=ctx.user,
            entity_type="quotation",
            entity_id=quotation.id,
            summary=f"{quotation.quote_number} for {customer.name}: {quotation.total}",
        )
        self.db.commit()
        self.db.refresh(quotation)
        return quotation

    def update(self, ctx: AuthContext, quotation_id: uuid.UUID, data: QuotationUpdate) -> Quotation:
        quotation = self._lock(quotation_id)
        if quotation.status not in QuotationStatus.EDITABLE:
            raise BusinessRuleError(
                f"Only draft or sent quotations can be edited (this one is {quotation.status})"
            )
        changes = data.model_dump(exclude_unset=True, exclude={"lines"})
        for field in ("customer_id", "quote_date", "valid_until", "prices_include_tax"):
            if field in changes and changes[field] is None:
                raise BusinessRuleError(f"{field} cannot be null")
        if changes.get("customer_id"):
            self._customer(changes["customer_id"])
        if "branch_id" in changes:
            self._check_branch(changes["branch_id"])
        pricing_changed = (
            "prices_include_tax" in changes
            and changes["prices_include_tax"] != quotation.prices_include_tax
        )
        for key, value in changes.items():
            setattr(quotation, key, value)
        if quotation.valid_until < quotation.quote_date:
            raise BusinessRuleError("valid_until cannot be before quote_date")
        if data.lines is not None:
            build_document_lines(self.db, quotation, data.lines, QuotationLine)
        elif pricing_changed:
            build_document_lines(self.db, quotation, lines_as_input(quotation), QuotationLine)
        self.audit.log(
            "sales.quotation_update",
            actor=ctx.user,
            entity_type="quotation",
            entity_id=quotation.id,
            summary=f"{quotation.quote_number} updated: total {quotation.total}",
        )
        self.db.commit()
        self.db.refresh(quotation)
        return quotation

    def delete(self, ctx: AuthContext, quotation_id: uuid.UUID) -> None:
        quotation = self._lock(quotation_id)
        if quotation.status != QuotationStatus.DRAFT:
            raise BusinessRuleError("Only draft quotations can be deleted. Decline it instead.")
        self.audit.log(
            "sales.quotation_delete",
            actor=ctx.user,
            entity_type="quotation",
            entity_id=quotation.id,
            summary=f"Deleted {quotation.quote_number}",
        )
        self.db.delete(quotation)
        self.db.commit()

    def set_status(self, ctx: AuthContext, quotation_id: uuid.UUID, status: str) -> Quotation:
        quotation = self._lock(quotation_id)
        allowed = _TRANSITIONS.get(quotation.status, set())
        if status not in allowed:
            raise BusinessRuleError(
                f"A {quotation.status.lower()} quotation cannot be marked {status.lower()}"
            )
        previous = quotation.status
        quotation.status = status
        self.audit.log(
            f"sales.quotation_{status.lower()}",
            actor=ctx.user,
            entity_type="quotation",
            entity_id=quotation.id,
            summary=f"{quotation.quote_number} marked {status.lower()}",
            changes={"status": {"from": previous, "to": status}},
        )
        self.db.commit()
        self.db.refresh(quotation)
        return quotation

    def convert(
        self, ctx: AuthContext, quotation_id: uuid.UUID, data: ConvertQuotation
    ) -> SalesInvoice:
        """Create a draft invoice with the quotation's lines and prices."""
        quotation = self._lock(quotation_id)
        if quotation.status == QuotationStatus.CONVERTED:
            raise BusinessRuleError("This quotation has already been converted to an invoice")
        if quotation.status == QuotationStatus.DECLINED:
            raise BusinessRuleError("A declined quotation cannot be converted")
        customer = self._customer(quotation.customer_id)
        sales = SalesService(self.db)
        sales._check_refs({"warehouse_id": data.warehouse_id})

        invoice_date = data.invoice_date or local_today()
        notes = f"From quotation {quotation.quote_number}."
        if quotation.notes:
            notes = f"{notes} {quotation.notes}"
        invoice = SalesInvoice(
            customer_id=customer.id,
            branch_id=quotation.branch_id,
            warehouse_id=data.warehouse_id,
            invoice_date=invoice_date,
            due_date=invoice_date + timedelta(days=customer.payment_terms_days),
            status=InvoiceStatus.DRAFT,
            currency=quotation.currency,
            prices_include_tax=quotation.prices_include_tax,
            customer_reference=quotation.customer_reference,
            notes=notes[:2000],
            created_by_id=ctx.user.id,
        )
        self.db.add(invoice)
        build_document_lines(self.db, invoice, lines_as_input(quotation), SalesInvoiceLine)
        self.db.flush()
        quotation.status = QuotationStatus.CONVERTED
        quotation.invoice_id = invoice.id
        self.audit.log(
            "sales.quotation_convert",
            actor=ctx.user,
            entity_type="quotation",
            entity_id=quotation.id,
            summary=f"{quotation.quote_number} converted to a draft invoice",
            changes={"invoice_id": invoice.id},
        )
        self.db.commit()
        self.db.refresh(invoice)
        return invoice
