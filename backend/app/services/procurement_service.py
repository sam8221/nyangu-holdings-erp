"""Purchase orders (draft, approve, cancel, close) and goods received notes."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.auth.permissions import Perm
from app.config import get_settings
from app.models.inventory import Warehouse
from app.models.organization import Branch
from app.models.partners import Product, Supplier
from app.models.procurement import (
    GoodsReceipt,
    GoodsReceiptLine,
    POStatus,
    PurchaseOrder,
    PurchaseOrderLine,
)
from app.repositories.query import get_for_update_or_404, get_or_404, paginate, search_clause
from app.schemas.common import Page, PageParams
from app.schemas.procurement import GRNCreate, POCreate, POLineIn, POUpdate
from app.services.audit import AuditService
from app.services.base import require_active, require_exists
from app.services.inventory_service import InventoryService
from app.services.notifications import NotificationService
from app.services.pricing import document_totals, line_amounts
from app.utils.exceptions import BusinessRuleError
from app.utils.money import money, qty
from app.utils.sequences import next_number
from app.utils.time import local_today, utcnow


class ProcurementService:
    PO_SORT = {
        "po_number": PurchaseOrder.po_number,
        "order_date": PurchaseOrder.order_date,
        "expected_date": PurchaseOrder.expected_date,
        "total": PurchaseOrder.total,
        "created_at": PurchaseOrder.created_at,
    }
    GRN_SORT = {"received_date": GoodsReceipt.received_date, "grn_number": GoodsReceipt.grn_number}

    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.notifications = NotificationService(db)

    # ================================================================== queries
    def list_orders(
        self,
        params: PageParams,
        *,
        status: str | None,
        supplier_id: uuid.UUID | None,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        stmt = select(PurchaseOrder).join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        if status:
            stmt = stmt.where(PurchaseOrder.status == status)
        if supplier_id:
            stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
        if date_from:
            stmt = stmt.where(PurchaseOrder.order_date >= date_from)
        if date_to:
            stmt = stmt.where(PurchaseOrder.order_date <= date_to)
        if params.search:
            stmt = stmt.where(
                search_clause(
                    params.search,
                    PurchaseOrder.po_number,
                    PurchaseOrder.supplier_reference,
                    Supplier.name,
                    Supplier.code,
                )
            )
        items, total = paginate(
            self.db, stmt, params, self.PO_SORT, ("created_at", "desc"), PurchaseOrder.id
        )
        return Page.build(items, total, params).model_dump()

    def get_order(self, order_id: uuid.UUID) -> PurchaseOrder:
        return get_or_404(self.db, PurchaseOrder, order_id, "Purchase order")

    def list_receipts(
        self,
        params: PageParams,
        *,
        purchase_order_id: uuid.UUID | None,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        stmt = select(GoodsReceipt)
        if purchase_order_id:
            stmt = stmt.where(GoodsReceipt.purchase_order_id == purchase_order_id)
        if date_from:
            stmt = stmt.where(GoodsReceipt.received_date >= date_from)
        if date_to:
            stmt = stmt.where(GoodsReceipt.received_date <= date_to)
        if params.search:
            stmt = stmt.where(
                search_clause(params.search, GoodsReceipt.grn_number, GoodsReceipt.delivery_note)
            )
        items, total = paginate(
            self.db, stmt, params, self.GRN_SORT, ("received_date", "desc"), GoodsReceipt.id
        )
        return Page.build(items, total, params).model_dump()

    def get_receipt(self, receipt_id: uuid.UUID) -> GoodsReceipt:
        return get_or_404(self.db, GoodsReceipt, receipt_id, "Goods receipt")

    # ================================================================== drafts
    def _lock(self, order_id: uuid.UUID) -> PurchaseOrder:
        return get_for_update_or_404(self.db, PurchaseOrder, order_id, "Purchase order")

    def _check_refs(self, values: dict[str, Any]) -> None:
        checks = (("supplier_id", Supplier), ("warehouse_id", Warehouse), ("branch_id", Branch))
        for field, model in checks:
            if values.get(field):
                require_active(require_exists(self.db, model, values[field], field), field)

    def _build_lines(self, order: PurchaseOrder, lines: list[POLineIn]) -> None:
        order.lines.clear()
        self.db.flush()
        amounts = []
        for number, line in enumerate(lines, start=1):
            field = f"lines.{number - 1}.product_id"
            product = require_exists(self.db, Product, line.product_id, field)
            require_active(product, field)
            unit_cost = line.unit_cost if line.unit_cost is not None else product.cost_price
            tax_rate = line.tax_rate if line.tax_rate is not None else product.tax_rate
            calc = line_amounts(line.quantity, unit_cost, Decimal(0), tax_rate)
            amounts.append(calc)
            order.lines.append(
                PurchaseOrderLine(
                    line_no=number,
                    product_id=product.id,
                    description=line.description or product.name,
                    quantity=line.quantity,
                    unit_cost=money(unit_cost),
                    tax_rate=tax_rate,
                    line_subtotal=calc.subtotal,
                    line_tax=calc.tax,
                    line_total=calc.total,
                    received_quantity=Decimal(0),
                )
            )
        totals = document_totals(amounts)
        order.subtotal = totals.subtotal
        order.tax_total = totals.tax_total
        order.total = totals.total

    def create_order(self, ctx: AuthContext, data: POCreate) -> PurchaseOrder:
        values = data.model_dump(exclude={"lines"})
        self._check_refs(values)
        order = PurchaseOrder(
            **{**values, "order_date": data.order_date or local_today()},
            po_number=next_number(self.db, "PO"),
            status=POStatus.DRAFT,
            currency=get_settings().DEFAULT_CURRENCY,
            created_by_id=ctx.user.id,
        )
        self.db.add(order)
        self._build_lines(order, data.lines)
        self.db.flush()
        self.audit.log(
            "procurement.po_create",
            actor=ctx.user,
            entity_type="purchase_order",
            entity_id=order.id,
            summary=f"{order.po_number} for {order.supplier.name}: {order.total}",
        )
        self.notifications.notify_permission(
            Perm.PROCUREMENT_APPROVE,
            f"Purchase order {order.po_number} awaiting approval",
            f"{ctx.user.full_name} raised {order.po_number} to {order.supplier.name} "
            f"for {order.total} {order.currency}.",
            category="APPROVAL",
            entity_type="purchase_order",
            entity_id=order.id,
            exclude_user_id=ctx.user.id,
        )
        self.db.commit()
        self.db.refresh(order)
        return order

    def update_order(self, ctx: AuthContext, order_id: uuid.UUID, data: POUpdate) -> PurchaseOrder:
        order = self._lock(order_id)
        if order.status != POStatus.DRAFT:
            raise BusinessRuleError("Only draft purchase orders can be edited")
        changes = data.model_dump(exclude_unset=True, exclude={"lines"})
        for field in ("supplier_id", "warehouse_id", "order_date"):
            if field in changes and changes[field] is None:
                raise BusinessRuleError(f"{field} cannot be null")
        self._check_refs(changes)
        for key, value in changes.items():
            setattr(order, key, value)
        if order.expected_date and order.expected_date < order.order_date:
            raise BusinessRuleError("expected_date cannot be before order_date")
        if data.lines is not None:
            self._build_lines(order, data.lines)
        self.audit.log(
            "procurement.po_update",
            actor=ctx.user,
            entity_type="purchase_order",
            entity_id=order.id,
            summary=f"{order.po_number} updated: total {order.total}",
        )
        self.db.commit()
        self.db.refresh(order)
        return order

    def delete_order(self, ctx: AuthContext, order_id: uuid.UUID) -> None:
        order = self._lock(order_id)
        if order.status != POStatus.DRAFT:
            raise BusinessRuleError("Only drafts can be deleted. Cancel an approved order instead.")
        self.audit.log(
            "procurement.po_delete",
            actor=ctx.user,
            entity_type="purchase_order",
            entity_id=order.id,
            summary=f"Deleted draft {order.po_number}",
        )
        self.db.delete(order)
        self.db.commit()

    # ================================================================== lifecycle
    def approve_order(self, ctx: AuthContext, order_id: uuid.UUID) -> PurchaseOrder:
        order = self._lock(order_id)
        if order.status != POStatus.DRAFT:
            raise BusinessRuleError(f"Only drafts can be approved (this order is {order.status})")
        require_active(order.supplier, "supplier_id")
        order.status = POStatus.APPROVED
        order.approved_by_id = ctx.user.id
        order.approved_at = utcnow()
        self.audit.log(
            "procurement.po_approve",
            actor=ctx.user,
            entity_type="purchase_order",
            entity_id=order.id,
            summary=f"Approved {order.po_number} ({order.total})",
        )
        if order.created_by_id:
            self.notifications.notify(
                [order.created_by_id],
                f"Purchase order {order.po_number} approved",
                f"{order.po_number} to {order.supplier.name} was approved and can be sent.",
                category="SUCCESS",
                entity_type="purchase_order",
                entity_id=order.id,
                exclude_user_id=ctx.user.id,
            )
        self.db.commit()
        self.db.refresh(order)
        return order

    def cancel_order(self, ctx: AuthContext, order_id: uuid.UUID, reason: str) -> PurchaseOrder:
        order = self._lock(order_id)
        if order.status not in (POStatus.DRAFT, POStatus.APPROVED):
            raise BusinessRuleError(
                "Only orders with nothing received can be cancelled. Close a partly "
                "received order instead."
            )
        previous = order.status
        order.status = POStatus.CANCELLED
        order.cancelled_by_id = ctx.user.id
        order.cancelled_at = utcnow()
        order.cancel_reason = reason
        self.audit.log(
            "procurement.po_cancel",
            actor=ctx.user,
            entity_type="purchase_order",
            entity_id=order.id,
            summary=f"Cancelled {order.po_number}: {reason}",
            changes={"status": {"from": previous, "to": POStatus.CANCELLED}},
        )
        self.db.commit()
        self.db.refresh(order)
        return order

    def close_order(self, ctx: AuthContext, order_id: uuid.UUID, reason: str) -> PurchaseOrder:
        order = self._lock(order_id)
        if order.status != POStatus.PARTIALLY_RECEIVED:
            raise BusinessRuleError("Only partly received orders can be closed")
        order.status = POStatus.CLOSED
        self.audit.log(
            "procurement.po_close",
            actor=ctx.user,
            entity_type="purchase_order",
            entity_id=order.id,
            summary=f"Closed {order.po_number} short: {reason}",
        )
        self.db.commit()
        self.db.refresh(order)
        return order

    # ================================================================== receiving
    def receive(self, ctx: AuthContext, data: GRNCreate) -> GoodsReceipt:
        order = self._lock(data.purchase_order_id)
        if order.status not in POStatus.RECEIVABLE:
            raise BusinessRuleError(
                f"Goods can only be received against approved orders (this one is {order.status})"
            )
        warehouse_id = data.warehouse_id or order.warehouse_id
        warehouse = require_exists(self.db, Warehouse, warehouse_id, "warehouse_id")
        require_active(warehouse, "warehouse_id")
        received_date = data.received_date or local_today()
        if received_date < order.order_date:
            raise BusinessRuleError("received_date cannot be before the order date")

        lines_by_id = {line.id: line for line in order.lines}
        receipt = GoodsReceipt(
            grn_number=next_number(self.db, "GRN"),
            purchase_order_id=order.id,
            warehouse_id=warehouse.id,
            received_date=received_date,
            delivery_note=data.delivery_note,
            notes=data.notes,
            received_by_id=ctx.user.id,
        )
        self.db.add(receipt)
        self.db.flush()
        inventory = InventoryService(self.db)
        for i, line_in in enumerate(data.lines):
            po_line = lines_by_id.get(line_in.purchase_order_line_id)
            if po_line is None:
                raise BusinessRuleError(
                    f"lines.{i}: that line does not belong to {order.po_number}",
                    errors=[{"field": f"lines.{i}.purchase_order_line_id", "message": "Unknown"}],
                )
            quantity = qty(line_in.quantity)
            if quantity > po_line.outstanding_quantity:
                raise BusinessRuleError(
                    f"Cannot receive {quantity} of {po_line.product.sku}: only "
                    f"{po_line.outstanding_quantity} outstanding on {order.po_number}"
                )
            unit_cost = money(
                line_in.unit_cost if line_in.unit_cost is not None else po_line.unit_cost
            )
            receipt.lines.append(
                GoodsReceiptLine(
                    purchase_order_line_id=po_line.id,
                    product_id=po_line.product_id,
                    quantity=quantity,
                    unit_cost=unit_cost,
                )
            )
            po_line.received_quantity = po_line.received_quantity + quantity
            if po_line.product.is_stocked:
                inventory.receive(
                    product=po_line.product,
                    warehouse_id=warehouse.id,
                    quantity=quantity,
                    unit_cost=unit_cost,
                    actor=ctx.user,
                    reference_type="GOODS_RECEIPT",
                    reference_id=receipt.id,
                    reference_number=receipt.grn_number,
                )

        fully = all(line.received_quantity >= line.quantity for line in order.lines)
        order.status = POStatus.RECEIVED if fully else POStatus.PARTIALLY_RECEIVED
        self.audit.log(
            "procurement.goods_receive",
            actor=ctx.user,
            entity_type="goods_receipt",
            entity_id=receipt.id,
            summary=f"{receipt.grn_number} against {order.po_number} into {warehouse.code}",
        )
        if order.created_by_id:
            self.notifications.notify(
                [order.created_by_id],
                f"Goods received for {order.po_number}",
                f"{receipt.grn_number} recorded; the order is now "
                f"{order.status.replace('_', ' ').lower()}.",
                entity_type="purchase_order",
                entity_id=order.id,
                exclude_user_id=ctx.user.id,
            )
        self.db.commit()
        self.db.refresh(receipt)
        return receipt
