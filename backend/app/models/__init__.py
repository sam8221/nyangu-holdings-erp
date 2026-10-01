"""Import every model here so Alembic autogenerate and relationship resolution can see them."""

from app.models.assets import Asset, AssetCategory
from app.models.base import Base
from app.models.finance import Expense, ExpenseCategory, SupplierBill, SupplierPayment
from app.models.hr import Employee, LeaveRequest
from app.models.inventory import StockLevel, StockMovement, Warehouse
from app.models.organization import Branch, Company, Department, SystemSetting
from app.models.partners import Customer, Product, ProductCategory, Supplier
from app.models.procurement import GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine
from app.models.rbac import Permission, Role, role_permissions, user_roles
from app.models.sales import (
    CustomerPayment,
    Quotation,
    QuotationLine,
    SalesInvoice,
    SalesInvoiceLine,
)
from app.models.system import AuditLog, DocumentSequence, Notification, PasswordResetToken
from app.models.token import RefreshToken, RevokedAccessToken
from app.models.user import User, UserStatus

__all__ = [
    "Asset",
    "AssetCategory",
    "AuditLog",
    "Base",
    "Branch",
    "Company",
    "Customer",
    "CustomerPayment",
    "Department",
    "DocumentSequence",
    "Employee",
    "Expense",
    "ExpenseCategory",
    "GoodsReceipt",
    "GoodsReceiptLine",
    "LeaveRequest",
    "Notification",
    "PasswordResetToken",
    "Permission",
    "Product",
    "ProductCategory",
    "PurchaseOrder",
    "PurchaseOrderLine",
    "Quotation",
    "QuotationLine",
    "RefreshToken",
    "RevokedAccessToken",
    "Role",
    "SalesInvoice",
    "SalesInvoiceLine",
    "Supplier",
    "SupplierBill",
    "SupplierPayment",
    "StockLevel",
    "StockMovement",
    "SystemSetting",
    "User",
    "UserStatus",
    "Warehouse",
    "role_permissions",
    "user_roles",
]
