"""Warehouses and the stock engine. Every quantity change goes through ``change_stock``."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, lazyload

from app.auth.dependencies import AuthContext
from app.auth.permissions import Perm
from app.models import User
from app.models.inventory import MovementType, StockLevel, StockMovement, Warehouse
from app.models.organization import Branch
from app.models.partners import Product
from app.repositories.query import get_or_404, paginate, search_clause
from app.schemas.common import Page, PageParams
from app.schemas.inventory import AdjustmentCreate, TransferCreate
from app.services.audit import AuditService
from app.services.base import require_active, require_exists
from app.services.master_data import MasterDataService
from app.services.notifications import NotificationService
from app.services.settings_service import SettingsService
from app.utils.exceptions import BusinessRuleError
from app.utils.money import ZERO, money, qty
from app.utils.sequences import next_number
from app.utils.time import start_of_local_day


class WarehouseService(MasterDataService):
    model = Warehouse
    label = "Warehouse"
    entity_type = "warehouse"
    action_prefix = "warehouses"
    unique_fields = {"code": "warehouse code"}
    required_fields = ("code", "name", "is_active")
    sort_fields = {
        "code": Warehouse.code,
        "name": Warehouse.name,
        "created_at": Warehouse.created_at,
    }
    default_sort = ("code", "asc")
    search_columns = (Warehouse.code, Warehouse.name)
    audited_fields = ("code", "name", "branch_id", "address", "is_active")

    def validate(self, values: dict[str, Any], existing: Any | None) -> None:
        if values.get("branch_id"):
            require_active(
                require_exists(self.db, Branch, values["branch_id"], "branch_id"), "branch_id"
            )
        if existing is not None and values.get("is_active") is False and existing.is_active:
            on_hand = self.db.scalar(
                select(func.coalesce(func.sum(StockLevel.quantity), 0)).where(
                    StockLevel.warehouse_id == existing.id
                )
            )
            if on_hand and Decimal(on_hand) > 0:
                raise BusinessRuleError(
                    "This warehouse still holds stock. Transfer it out before deactivating."
                )

    def describe(self, obj: Any) -> str:
        return f"{obj.code} {obj.name}"


class InventoryService:
    LEVEL_SORT = {"quantity": StockLevel.quantity, "updated_at": StockLevel.updated_at}
    MOVEMENT_SORT = {"created_at": StockMovement.created_at, "quantity": StockMovement.quantity}

    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    # ================================================================== engine
    def _lock_level(self, product_id: uuid.UUID, warehouse_id: uuid.UUID) -> StockLevel:
        self.db.execute(
            insert(StockLevel)
            .values(id=uuid.uuid4(), product_id=product_id, warehouse_id=warehouse_id, quantity=0)
            .on_conflict_do_nothing(constraint="uq_stock_levels_product_warehouse")
        )
        # lazyload: a joined load here would refresh the Product and discard unsaved changes
        # (such as a new average cost) because of populate_existing.
        return self.db.scalars(
            select(StockLevel)
            .options(lazyload(StockLevel.product), lazyload(StockLevel.warehouse))
            .where(StockLevel.product_id == product_id, StockLevel.warehouse_id == warehouse_id)
            .with_for_update(of=StockLevel)
            .execution_options(populate_existing=True)
        ).one()

    def on_hand(self, product_id: uuid.UUID, warehouse_id: uuid.UUID | None = None) -> Decimal:
        stmt = select(func.coalesce(func.sum(StockLevel.quantity), 0)).where(
            StockLevel.product_id == product_id
        )
        if warehouse_id:
            stmt = stmt.where(StockLevel.warehouse_id == warehouse_id)
        return Decimal(self.db.scalar(stmt) or 0)

    def change_stock(
        self,
        *,
        product: Product,
        warehouse_id: uuid.UUID,
        quantity: Decimal,
        movement_type: str,
        actor: User | None,
        unit_cost: Decimal | None = None,
        reference_type: str | None = None,
        reference_id: uuid.UUID | None = None,
        reference_number: str | None = None,
        notes: str | None = None,
        low_stock_alert: bool = True,
    ) -> StockMovement:
        """Apply a signed quantity change and write the ledger entry. Never goes negative."""
        quantity = qty(quantity)
        if quantity == 0:
            raise BusinessRuleError("Stock movements must change the quantity")
        if not product.is_stocked:
            raise BusinessRuleError(f"{product.sku} is a service and does not hold stock")

        total_before = self.on_hand(product.id)
        level = self._lock_level(product.id, warehouse_id)
        new_quantity = qty(level.quantity + quantity)
        if new_quantity < 0:
            warehouse = self.db.get(Warehouse, warehouse_id)
            where = warehouse.code if warehouse else "the warehouse"
            raise BusinessRuleError(
                f"Insufficient stock of {product.sku} in {where}: "
                f"{level.quantity} available, {-quantity} required"
            )
        level.quantity = new_quantity
        movement = StockMovement(
            product_id=product.id,
            warehouse_id=warehouse_id,
            movement_type=movement_type,
            quantity=quantity,
            balance_after=new_quantity,
            unit_cost=money(unit_cost if unit_cost is not None else product.cost_price),
            reference_type=reference_type,
            reference_id=reference_id,
            reference_number=reference_number,
            notes=notes,
            created_by_id=actor.id if actor else None,
        )
        self.db.add(movement)
        self.db.flush()
        if quantity < 0 and low_stock_alert:
            self._maybe_alert_low_stock(product, total_before, total_before + quantity)
        return movement

    def receive(
        self,
        *,
        product: Product,
        warehouse_id: uuid.UUID,
        quantity: Decimal,
        unit_cost: Decimal,
        actor: User | None,
        **reference: Any,
    ) -> StockMovement:
        """Receive goods and update the product's weighted average cost."""
        total_before = self.on_hand(product.id)
        incoming = qty(quantity)
        if total_before + incoming > 0:
            product.cost_price = money(
                (total_before * product.cost_price + incoming * unit_cost)
                / (total_before + incoming)
            )
        return self.change_stock(
            product=product,
            warehouse_id=warehouse_id,
            quantity=incoming,
            movement_type=MovementType.RECEIPT,
            actor=actor,
            unit_cost=unit_cost,
            **reference,
        )

    def _maybe_alert_low_stock(self, product: Product, before: Decimal, after: Decimal) -> None:
        threshold = product.reorder_level
        if threshold <= 0 or not (before > threshold >= after):
            return  # only alert when the level crosses the threshold
        if not SettingsService(self.db).get("low_stock_alerts_enabled"):
            return
        NotificationService(self.db).notify_permission(
            Perm.INVENTORY_ADJUST,
            f"Low stock: {product.sku}",
            f"{product.name} is down to {after} {product.unit} (reorder level {threshold}).",
            category="ALERT",
            entity_type="product",
            entity_id=product.id,
        )

    # ================================================================== queries
    def stock_levels(
        self,
        params: PageParams,
        *,
        warehouse_id: uuid.UUID | None,
        product_id: uuid.UUID | None,
        category_id: uuid.UUID | None,
        include_zero: bool,
    ) -> dict[str, Any]:
        stmt = select(StockLevel).join(Product, Product.id == StockLevel.product_id)
        if warehouse_id:
            stmt = stmt.where(StockLevel.warehouse_id == warehouse_id)
        if product_id:
            stmt = stmt.where(StockLevel.product_id == product_id)
        if category_id:
            stmt = stmt.where(Product.category_id == category_id)
        if not include_zero:
            stmt = stmt.where(StockLevel.quantity > 0)
        if params.search:
            stmt = stmt.where(search_clause(params.search, Product.sku, Product.name))
        sort = {**self.LEVEL_SORT, "sku": Product.sku, "name": Product.name}
        items, total = paginate(self.db, stmt, params, sort, ("sku", "asc"), StockLevel.id)
        return Page.build(items, total, params).model_dump()

    def product_stock(self, product_id: uuid.UUID) -> dict[str, Any]:
        product = get_or_404(self.db, Product, product_id, "Product")
        levels = self.db.scalars(
            select(StockLevel)
            .join(Warehouse, Warehouse.id == StockLevel.warehouse_id)
            .where(StockLevel.product_id == product.id)
            .order_by(Warehouse.code)
        ).all()
        total = sum((lvl.quantity for lvl in levels), ZERO)
        return {
            "product_id": product.id,
            "sku": product.sku,
            "name": product.name,
            "unit": product.unit,
            "reorder_level": product.reorder_level,
            "total_quantity": total,
            "is_low": product.reorder_level > 0 and total <= product.reorder_level,
            "stock_value": money(total * product.cost_price),
            "warehouses": [
                {
                    "warehouse_id": lvl.warehouse_id,
                    "code": lvl.warehouse.code,
                    "name": lvl.warehouse.name,
                    "quantity": lvl.quantity,
                }
                for lvl in levels
            ],
        }

    def low_stock(self, params: PageParams) -> dict[str, Any]:
        totals = (
            select(StockLevel.product_id, func.sum(StockLevel.quantity).label("total"))
            .group_by(StockLevel.product_id)
            .subquery()
        )
        on_hand = func.coalesce(totals.c.total, 0)
        stmt = (
            select(Product, on_hand.label("on_hand"))
            .outerjoin(totals, totals.c.product_id == Product.id)
            .where(
                Product.is_active.is_(True),
                Product.product_type == "GOODS",
                Product.reorder_level > 0,
                on_hand <= Product.reorder_level,
            )
        )
        if params.search:
            stmt = stmt.where(search_clause(params.search, Product.sku, Product.name))
        total_count = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.db.execute(
            stmt.order_by(Product.sku).offset(params.offset).limit(params.page_size)
        ).all()
        items = [
            {
                "product_id": p.id,
                "sku": p.sku,
                "name": p.name,
                "unit": p.unit,
                "on_hand": Decimal(q),
                "reorder_level": p.reorder_level,
                "shortfall": p.reorder_level - Decimal(q),
            }
            for p, q in rows
        ]
        return Page.build(items, total_count, params).model_dump()

    def movements(
        self,
        params: PageParams,
        *,
        product_id: uuid.UUID | None,
        warehouse_id: uuid.UUID | None,
        movement_type: str | None,
        reference_number: str | None,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        stmt = select(StockMovement)
        if product_id:
            stmt = stmt.where(StockMovement.product_id == product_id)
        if warehouse_id:
            stmt = stmt.where(StockMovement.warehouse_id == warehouse_id)
        if movement_type:
            stmt = stmt.where(StockMovement.movement_type == movement_type)
        if reference_number:
            stmt = stmt.where(StockMovement.reference_number == reference_number.upper())
        if date_from:
            stmt = stmt.where(StockMovement.created_at >= start_of_local_day(date_from))
        if date_to:
            stmt = stmt.where(
                StockMovement.created_at < start_of_local_day(date_to + timedelta(days=1))
            )
        items, total = paginate(
            self.db, stmt, params, self.MOVEMENT_SORT, ("created_at", "desc"), StockMovement.id
        )
        return Page.build(items, total, params).model_dump()

    # ================================================================== commands
    def _warehouse(self, warehouse_id: uuid.UUID, field: str) -> Warehouse:
        warehouse = require_exists(self.db, Warehouse, warehouse_id, field)
        require_active(warehouse, field)
        return warehouse

    def _product(self, product_id: uuid.UUID, field: str) -> Product:
        product = require_exists(self.db, Product, product_id, field)
        if not product.is_stocked:
            raise BusinessRuleError(f"{product.sku} is a service and does not hold stock")
        return product

    def adjust(self, ctx: AuthContext, data: AdjustmentCreate) -> dict[str, Any]:
        warehouse = self._warehouse(data.warehouse_id, "warehouse_id")
        reference = next_number(self.db, "ADJ")
        movements = []
        for i, line in enumerate(data.lines):
            product = self._product(line.product_id, f"lines.{i}.product_id")
            if line.counted_quantity is not None:
                change = qty(line.counted_quantity) - self.on_hand(product.id, warehouse.id)
                if change == 0:
                    continue  # the count matches the system
            else:
                change = qty(line.quantity_change or 0)
            movements.append(
                self.change_stock(
                    product=product,
                    warehouse_id=warehouse.id,
                    quantity=change,
                    movement_type=MovementType.ADJUSTMENT,
                    actor=ctx.user,
                    reference_type="ADJUSTMENT",
                    reference_number=reference,
                    notes=data.reason,
                )
            )
        if not movements:
            raise BusinessRuleError("Nothing to adjust: every counted quantity matches the system")
        self.audit.log(
            "inventory.adjust",
            actor=ctx.user,
            entity_type="warehouse",
            entity_id=warehouse.id,
            summary=f"Stock adjustment {reference} in {warehouse.code}: {data.reason}",
            changes={
                "lines": [
                    {"product_id": m.product_id, "quantity": m.quantity, "balance": m.balance_after}
                    for m in movements
                ]
            },
        )
        self.db.commit()
        return {"reference_number": reference, "movements": movements}

    def transfer(self, ctx: AuthContext, data: TransferCreate) -> dict[str, Any]:
        if data.from_warehouse_id == data.to_warehouse_id:
            raise BusinessRuleError("Source and destination warehouses must differ")
        source = self._warehouse(data.from_warehouse_id, "from_warehouse_id")
        target = self._warehouse(data.to_warehouse_id, "to_warehouse_id")
        reference = next_number(self.db, "TRF")
        movements = []
        for i, line in enumerate(data.lines):
            product = self._product(line.product_id, f"lines.{i}.product_id")
            common = {
                "product": product,
                "actor": ctx.user,
                "reference_type": "TRANSFER",
                "reference_number": reference,
                "notes": data.notes,
                "low_stock_alert": False,  # the company-wide total does not change
            }
            movements.append(
                self.change_stock(
                    warehouse_id=source.id,
                    quantity=-line.quantity,
                    movement_type=MovementType.TRANSFER_OUT,
                    **common,
                )
            )
            movements.append(
                self.change_stock(
                    warehouse_id=target.id,
                    quantity=line.quantity,
                    movement_type=MovementType.TRANSFER_IN,
                    **common,
                )
            )
        self.audit.log(
            "inventory.transfer",
            actor=ctx.user,
            entity_type="warehouse",
            entity_id=source.id,
            summary=f"Transfer {reference} from {source.code} to {target.code}",
            changes={
                "lines": [
                    {"product_id": ln.product_id, "quantity": ln.quantity} for ln in data.lines
                ]
            },
        )
        self.db.commit()
        return {"reference_number": reference, "movements": movements}
