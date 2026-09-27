"""Fixed assets: register, assignment, disposal and depreciation schedules."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from app.auth.dependencies import AuthContext
from app.models.assets import Asset, AssetCategory
from app.models.hr import Employee, EmployeeStatus
from app.models.organization import Branch
from app.models.partners import Supplier
from app.repositories.query import get_for_update_or_404
from app.schemas.assets import AssetAssign, AssetDispose
from app.services.base import require_active, require_exists
from app.services.master_data import MasterDataService
from app.utils.exceptions import BusinessRuleError
from app.utils.money import money
from app.utils.time import local_today, utcnow


class AssetCategoryService(MasterDataService):
    model = AssetCategory
    label = "Asset category"
    entity_type = "asset_category"
    action_prefix = "asset_categories"
    unique_fields = {"name": "category name"}
    required_fields = ("name", "depreciation_method", "useful_life_months", "is_active")
    sort_fields = {"name": AssetCategory.name, "created_at": AssetCategory.created_at}
    default_sort = ("name", "asc")
    search_columns = (AssetCategory.name,)
    audited_fields = (
        "name",
        "description",
        "depreciation_method",
        "useful_life_months",
        "is_active",
    )


class AssetService(MasterDataService):
    model = Asset
    label = "Asset"
    entity_type = "asset"
    action_prefix = "assets"
    number_field = "asset_tag"
    number_prefix = "AST"
    unique_fields = {"serial_number": "serial number"}
    required_fields = (
        "name",
        "category_id",
        "purchase_date",
        "purchase_cost",
        "salvage_value",
        "depreciation_method",
        "useful_life_months",
        "status",
    )
    sort_fields = {
        "asset_tag": Asset.asset_tag,
        "name": Asset.name,
        "purchase_date": Asset.purchase_date,
        "purchase_cost": Asset.purchase_cost,
        "created_at": Asset.created_at,
    }
    default_sort = ("asset_tag", "asc")
    search_columns = (Asset.asset_tag, Asset.name, Asset.serial_number, Asset.location)
    audited_fields = (
        "asset_tag",
        "name",
        "category_id",
        "branch_id",
        "assigned_employee_id",
        "supplier_id",
        "serial_number",
        "location",
        "purchase_date",
        "purchase_cost",
        "salvage_value",
        "depreciation_method",
        "useful_life_months",
        "status",
    )

    def defaults(self, values: dict[str, Any]) -> dict[str, Any]:
        category = require_exists(self.db, AssetCategory, values["category_id"], "category_id")
        require_active(category, "category_id")
        values["depreciation_method"] = (
            values.get("depreciation_method") or category.depreciation_method
        )
        values["useful_life_months"] = (
            values.get("useful_life_months") or category.useful_life_months
        )
        return values

    def validate(self, values: dict[str, Any], existing: Any | None) -> None:
        if existing is not None and existing.status == "DISPOSED":
            raise BusinessRuleError("Disposed assets cannot be changed")
        if values.get("category_id") and existing is not None:
            require_active(
                require_exists(self.db, AssetCategory, values["category_id"], "category_id"),
                "category_id",
            )
        if values.get("branch_id"):
            require_active(
                require_exists(self.db, Branch, values["branch_id"], "branch_id"), "branch_id"
            )
        if values.get("supplier_id"):
            require_exists(self.db, Supplier, values["supplier_id"], "supplier_id")
        purchase_date = values.get("purchase_date") or (
            existing.purchase_date if existing else None
        )
        if purchase_date and purchase_date > local_today():
            raise BusinessRuleError("purchase_date cannot be in the future")
        cost = values.get("purchase_cost", existing.purchase_cost if existing else None)
        salvage = values.get("salvage_value", existing.salvage_value if existing else None)
        if cost is not None and salvage is not None and salvage > cost:
            raise BusinessRuleError("salvage_value cannot exceed purchase_cost")

    def describe(self, obj: Any) -> str:
        return f"{obj.asset_tag} {obj.name}"

    # ------------------------------------------------------------------ actions
    def assign(self, ctx: AuthContext, asset_id: uuid.UUID, data: AssetAssign) -> Asset:
        asset = get_for_update_or_404(self.db, Asset, asset_id, "Asset")
        if asset.status == "DISPOSED":
            raise BusinessRuleError("Disposed assets cannot be assigned")
        previous = asset.assigned_employee_id
        if data.employee_id:
            employee = require_exists(self.db, Employee, data.employee_id, "employee_id")
            if employee.status == EmployeeStatus.TERMINATED:
                raise BusinessRuleError("Assets cannot be assigned to a terminated employee")
            asset.assigned_employee_id = employee.id
            asset.status = "IN_USE"
        else:
            asset.assigned_employee_id = None
            asset.status = "IN_STORE"
        if data.location is not None:
            asset.location = data.location
        self.audit.log(
            "assets.assign",
            actor=ctx.user,
            entity_type="asset",
            entity_id=asset.id,
            summary=f"{asset.asset_tag} "
            + ("assigned" if data.employee_id else "returned to store"),
            changes={"assigned_employee_id": {"from": previous, "to": data.employee_id}},
        )
        self.db.commit()
        self.db.refresh(asset)
        return asset

    def dispose(self, ctx: AuthContext, asset_id: uuid.UUID, data: AssetDispose) -> Asset:
        asset = get_for_update_or_404(self.db, Asset, asset_id, "Asset")
        if asset.status == "DISPOSED":
            raise BusinessRuleError("Asset is already disposed")
        if data.disposal_date < asset.purchase_date:
            raise BusinessRuleError("disposal_date cannot be before the purchase date")
        if data.disposal_date > local_today():
            raise BusinessRuleError("disposal_date cannot be in the future")
        asset.status = "DISPOSED"
        asset.disposal_date = data.disposal_date
        asset.disposal_value = money(data.disposal_value)
        asset.disposal_reason = data.reason
        asset.assigned_employee_id = None
        asset.disposed_by_id = ctx.user.id
        asset.disposed_at = utcnow()
        self.audit.log(
            "assets.dispose",
            actor=ctx.user,
            entity_type="asset",
            entity_id=asset.id,
            summary=f"Disposed {asset.asset_tag} for {asset.disposal_value}: {data.reason}",
            changes={
                "book_value": asset.book_value_at(data.disposal_date),
                "gain_loss": asset.disposal_gain_loss,
            },
        )
        self.db.commit()
        self.db.refresh(asset)
        return asset

    def schedule(self, asset_id: uuid.UUID) -> dict[str, Any]:
        asset = self.get(asset_id)
        years = []
        if asset.depreciation_method == "STRAIGHT_LINE":
            last_year = (
                asset.disposal_date.year
                if asset.disposal_date
                else _add_months(asset.purchase_date, asset.useful_life_months).year
            )
            first_year = asset.purchase_date.year
            for year in range(first_year, last_year + 1):
                opening = (
                    asset.purchase_cost
                    if year == first_year
                    else asset.book_value_at(date(year - 1, 12, 31))
                )
                closing = asset.book_value_at(date(year, 12, 31))
                years.append(
                    {
                        "year": year,
                        "opening_value": opening,
                        "depreciation": opening - closing,
                        "closing_value": closing,
                    }
                )
        return {
            "asset_id": asset.id,
            "asset_tag": asset.asset_tag,
            "method": asset.depreciation_method,
            "monthly_depreciation": money(asset.monthly_depreciation),
            "years": years,
        }


def _add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    return date(year, month_index % 12 + 1, 1)
