"""Import every model here so Alembic autogenerate and relationship resolution can see them."""

from app.models.base import Base
from app.models.hr import Employee, LeaveRequest
from app.models.inventory import StockLevel, StockMovement, Warehouse
from app.models.organization import Branch, Company, Department, SystemSetting
from app.models.partners import Customer, Product, ProductCategory, Supplier
from app.models.rbac import Permission, Role, role_permissions, user_roles
from app.models.sales import CustomerPayment, SalesInvoice, SalesInvoiceLine
from app.models.system import AuditLog, DocumentSequence, Notification, PasswordResetToken
from app.models.token import RefreshToken, RevokedAccessToken
from app.models.user import User, UserStatus

__all__ = [
    "AuditLog",
    "Base",
    "Branch",
    "Company",
    "Customer",
    "CustomerPayment",
    "Department",
    "DocumentSequence",
    "Employee",
    "LeaveRequest",
    "Notification",
    "PasswordResetToken",
    "Permission",
    "Product",
    "ProductCategory",
    "RefreshToken",
    "RevokedAccessToken",
    "Role",
    "SalesInvoice",
    "SalesInvoiceLine",
    "Supplier",
    "StockLevel",
    "StockMovement",
    "SystemSetting",
    "User",
    "UserStatus",
    "Warehouse",
    "role_permissions",
    "user_roles",
]
