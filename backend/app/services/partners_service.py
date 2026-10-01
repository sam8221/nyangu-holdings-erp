"""Customers, suppliers, product categories and products."""

from __future__ import annotations

from typing import Any

from app.models.partners import Customer, Product, ProductCategory, Supplier
from app.services.base import require_active, require_exists
from app.services.master_data import MasterDataService
from app.services.settings_service import SettingsService
from app.utils.exceptions import BusinessRuleError

_PARTY_FIELDS = (
    "code",
    "name",
    "tpin",
    "email",
    "phone",
    "address",
    "city",
    "contact_person",
    "payment_terms_days",
    "is_active",
    "notes",
)


class CustomerService(MasterDataService):
    model = Customer
    label = "Customer"
    entity_type = "customer"
    action_prefix = "customers"
    number_field = "code"
    number_prefix = "CUS"
    required_fields = ("name", "customer_type", "payment_terms_days", "is_active")
    sort_fields = {
        "code": Customer.code,
        "name": Customer.name,
        "created_at": Customer.created_at,
        "credit_limit": Customer.credit_limit,
    }
    default_sort = ("name", "asc")
    search_columns = (Customer.code, Customer.name, Customer.email, Customer.phone, Customer.tpin)
    audited_fields = (*_PARTY_FIELDS, "customer_type", "credit_limit")

    def defaults(self, values: dict[str, Any]) -> dict[str, Any]:
        if values.get("payment_terms_days") is None:
            values["payment_terms_days"] = SettingsService(self.db).get(
                "default_payment_terms_days"
            )
        return values

    def describe(self, obj: Any) -> str:
        return f"{obj.code} {obj.name}"


class SupplierService(MasterDataService):
    model = Supplier
    label = "Supplier"
    entity_type = "supplier"
    action_prefix = "suppliers"
    number_field = "code"
    number_prefix = "SUP"
    required_fields = ("name", "payment_terms_days", "is_active")
    sort_fields = {"code": Supplier.code, "name": Supplier.name, "created_at": Supplier.created_at}
    default_sort = ("name", "asc")
    search_columns = (Supplier.code, Supplier.name, Supplier.email, Supplier.phone, Supplier.tpin)
    audited_fields = (*_PARTY_FIELDS, "bank_name", "bank_branch", "bank_account_number")

    def defaults(self, values: dict[str, Any]) -> dict[str, Any]:
        if values.get("payment_terms_days") is None:
            values["payment_terms_days"] = SettingsService(self.db).get(
                "default_payment_terms_days"
            )
        return values

    def describe(self, obj: Any) -> str:
        return f"{obj.code} {obj.name}"


class CategoryService(MasterDataService):
    model = ProductCategory
    label = "Product category"
    entity_type = "product_category"
    action_prefix = "product_categories"
    unique_fields = {"name": "category name"}
    required_fields = ("name", "is_active")
    sort_fields = {"name": ProductCategory.name, "created_at": ProductCategory.created_at}
    default_sort = ("name", "asc")
    search_columns = (ProductCategory.name,)
    audited_fields = ("name", "description", "is_active")


class ProductService(MasterDataService):
    model = Product
    label = "Product"
    entity_type = "product"
    action_prefix = "products"
    number_field = "sku"  # item codes are numbered automatically when left blank
    number_prefix = "ITM"
    unique_fields = {"sku": "SKU", "barcode": "barcode"}
    required_fields = (
        "sku",
        "name",
        "product_type",
        "unit",
        "selling_price",
        "tax_rate",
        "reorder_level",
        "is_active",
    )
    sort_fields = {
        "sku": Product.sku,
        "name": Product.name,
        "selling_price": Product.selling_price,
        "created_at": Product.created_at,
    }
    default_sort = ("name", "asc")
    search_columns = (Product.sku, Product.name, Product.barcode)
    audited_fields = (
        "sku",
        "name",
        "description",
        "category_id",
        "product_type",
        "unit",
        "barcode",
        "cost_price",
        "selling_price",
        "tax_rate",
        "reorder_level",
        "is_active",
    )

    def defaults(self, values: dict[str, Any]) -> dict[str, Any]:
        if values.get("tax_rate") is None:
            values["tax_rate"] = SettingsService(self.db).get("default_vat_rate")
        if values.get("reorder_level") is None:
            values["reorder_level"] = 0
        return values

    def validate(self, values: dict[str, Any], existing: Any | None) -> None:
        if values.get("category_id"):
            category = require_exists(
                self.db, ProductCategory, values["category_id"], "category_id"
            )
            require_active(category, "category_id")
        if (
            existing is not None
            and values.get("product_type")
            and values["product_type"] != existing.product_type
            and self._has_stock_history(existing)
        ):
            raise BusinessRuleError("Product type cannot change once stock has been recorded")

    def _has_stock_history(self, product: Product) -> bool:
        # Stock tables arrive with the inventory module; import lazily to avoid a cycle.
        from sqlalchemy import func, select

        from app.models.inventory import StockMovement

        return bool(
            self.db.scalar(select(func.count()).where(StockMovement.product_id == product.id))
        )

    def describe(self, obj: Any) -> str:
        return f"{obj.sku} {obj.name}"
