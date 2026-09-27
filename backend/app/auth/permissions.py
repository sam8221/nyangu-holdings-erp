"""The permission catalogue and default system roles.

This module is the single source of truth for permissions. The seed script copies it into the
database. Permissions for later modules are defined now so roles can be configured ahead of time.

Format: ``module.action``, e.g. ``users.view`` or ``sales.approve``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Perm(StrEnum):
    # --- Administration ---
    USERS_VIEW = "users.view"
    USERS_CREATE = "users.create"
    USERS_UPDATE = "users.update"
    USERS_ASSIGN_ROLES = "users.assign_roles"
    USERS_RESET_PASSWORD = "users.reset_password"

    ROLES_VIEW = "roles.view"
    ROLES_CREATE = "roles.create"
    ROLES_UPDATE = "roles.update"
    ROLES_DELETE = "roles.delete"

    PERMISSIONS_VIEW = "permissions.view"

    SETTINGS_VIEW = "settings.view"
    SETTINGS_UPDATE = "settings.update"

    AUDIT_VIEW = "audit.view"

    # --- General ---
    DASHBOARD_VIEW = "dashboard.view"
    NOTIFICATIONS_VIEW = "notifications.view"

    REPORTS_VIEW = "reports.view"
    REPORTS_EXPORT = "reports.export"

    COMPANY_VIEW = "company.view"
    COMPANY_UPDATE = "company.update"

    # --- HR ---
    EMPLOYEES_VIEW = "employees.view"
    EMPLOYEES_CREATE = "employees.create"
    EMPLOYEES_UPDATE = "employees.update"
    EMPLOYEES_DELETE = "employees.delete"
    EMPLOYEES_VIEW_SALARY = "employees.view_salary"

    LEAVE_VIEW = "leave.view"
    LEAVE_CREATE = "leave.create"
    LEAVE_APPROVE = "leave.approve"

    # --- Sales & customers ---
    CUSTOMERS_VIEW = "customers.view"
    CUSTOMERS_CREATE = "customers.create"
    CUSTOMERS_UPDATE = "customers.update"
    CUSTOMERS_DELETE = "customers.delete"

    SALES_VIEW = "sales.view"
    SALES_CREATE = "sales.create"
    SALES_UPDATE = "sales.update"
    SALES_DELETE = "sales.delete"
    SALES_APPROVE = "sales.approve"

    # --- Procurement & suppliers ---
    SUPPLIERS_VIEW = "suppliers.view"
    SUPPLIERS_CREATE = "suppliers.create"
    SUPPLIERS_UPDATE = "suppliers.update"
    SUPPLIERS_DELETE = "suppliers.delete"

    PROCUREMENT_VIEW = "procurement.view"
    PROCUREMENT_CREATE = "procurement.create"
    PROCUREMENT_UPDATE = "procurement.update"
    PROCUREMENT_DELETE = "procurement.delete"
    PROCUREMENT_APPROVE = "procurement.approve"

    # --- Products & inventory ---
    PRODUCTS_VIEW = "products.view"
    PRODUCTS_CREATE = "products.create"
    PRODUCTS_UPDATE = "products.update"
    PRODUCTS_DELETE = "products.delete"

    INVENTORY_VIEW = "inventory.view"
    INVENTORY_ADJUST = "inventory.adjust"
    INVENTORY_TRANSFER = "inventory.transfer"

    # --- Finance ---
    FINANCE_VIEW = "finance.view"
    FINANCE_CREATE = "finance.create"
    FINANCE_UPDATE = "finance.update"
    FINANCE_APPROVE = "finance.approve"

    # --- Assets ---
    ASSETS_VIEW = "assets.view"
    ASSETS_CREATE = "assets.create"
    ASSETS_UPDATE = "assets.update"
    ASSETS_DELETE = "assets.delete"

    @property
    def module(self) -> str:
        return self.value.split(".", 1)[0]

    @property
    def action(self) -> str:
        return self.value.split(".", 1)[1]


PERMISSION_DESCRIPTIONS: dict[Perm, str] = {
    Perm.USERS_VIEW: "View user accounts",
    Perm.USERS_CREATE: "Create user accounts",
    Perm.USERS_UPDATE: "Edit, activate and deactivate user accounts",
    Perm.USERS_ASSIGN_ROLES: "Assign roles to users",
    Perm.USERS_RESET_PASSWORD: "Reset another user's password",
    Perm.ROLES_VIEW: "View roles",
    Perm.ROLES_CREATE: "Create roles",
    Perm.ROLES_UPDATE: "Edit roles and their permissions",
    Perm.ROLES_DELETE: "Delete custom roles",
    Perm.PERMISSIONS_VIEW: "View the permission catalogue",
    Perm.SETTINGS_VIEW: "View system settings",
    Perm.SETTINGS_UPDATE: "Change system settings",
    Perm.AUDIT_VIEW: "View audit logs",
    Perm.DASHBOARD_VIEW: "View the dashboard",
    Perm.NOTIFICATIONS_VIEW: "View notifications",
    Perm.REPORTS_VIEW: "View reports",
    Perm.REPORTS_EXPORT: "Export reports",
    Perm.COMPANY_VIEW: "View company and branch details",
    Perm.COMPANY_UPDATE: "Edit company and branch details",
    Perm.EMPLOYEES_VIEW: "View employees",
    Perm.EMPLOYEES_CREATE: "Create employees",
    Perm.EMPLOYEES_UPDATE: "Edit employees",
    Perm.EMPLOYEES_DELETE: "Delete employees",
    Perm.EMPLOYEES_VIEW_SALARY: "View employee salary information",
    Perm.LEAVE_VIEW: "View leave requests",
    Perm.LEAVE_CREATE: "Create leave requests",
    Perm.LEAVE_APPROVE: "Approve or reject leave requests",
    Perm.CUSTOMERS_VIEW: "View customers",
    Perm.CUSTOMERS_CREATE: "Create customers",
    Perm.CUSTOMERS_UPDATE: "Edit customers",
    Perm.CUSTOMERS_DELETE: "Delete customers",
    Perm.SALES_VIEW: "View sales, quotations and invoices",
    Perm.SALES_CREATE: "Create sales, quotations and invoices",
    Perm.SALES_UPDATE: "Edit sales documents",
    Perm.SALES_DELETE: "Delete or void sales documents",
    Perm.SALES_APPROVE: "Approve sales documents",
    Perm.SUPPLIERS_VIEW: "View suppliers",
    Perm.SUPPLIERS_CREATE: "Create suppliers",
    Perm.SUPPLIERS_UPDATE: "Edit suppliers",
    Perm.SUPPLIERS_DELETE: "Delete suppliers",
    Perm.PROCUREMENT_VIEW: "View purchase requests and orders",
    Perm.PROCUREMENT_CREATE: "Create purchase requests and orders",
    Perm.PROCUREMENT_UPDATE: "Edit purchase documents",
    Perm.PROCUREMENT_DELETE: "Delete or cancel purchase documents",
    Perm.PROCUREMENT_APPROVE: "Approve purchase documents",
    Perm.PRODUCTS_VIEW: "View products",
    Perm.PRODUCTS_CREATE: "Create products",
    Perm.PRODUCTS_UPDATE: "Edit products",
    Perm.PRODUCTS_DELETE: "Delete products",
    Perm.INVENTORY_VIEW: "View stock levels and movements",
    Perm.INVENTORY_ADJUST: "Adjust stock levels",
    Perm.INVENTORY_TRANSFER: "Transfer stock between locations",
    Perm.FINANCE_VIEW: "View financial records",
    Perm.FINANCE_CREATE: "Record expenses, receipts and payments",
    Perm.FINANCE_UPDATE: "Edit financial records",
    Perm.FINANCE_APPROVE: "Approve financial transactions",
    Perm.ASSETS_VIEW: "View assets",
    Perm.ASSETS_CREATE: "Register assets",
    Perm.ASSETS_UPDATE: "Edit assets",
    Perm.ASSETS_DELETE: "Dispose of or delete assets",
}

ALL_PERMISSIONS: frozenset[str] = frozenset(p.value for p in Perm)

# Modules that are about running the system, not the business.
ADMIN_MODULES = frozenset({"users", "roles", "permissions", "settings", "audit"})
# Modules every staff role can see.
_COMMON = {Perm.DASHBOARD_VIEW, Perm.NOTIFICATIONS_VIEW}


def _module(*modules: str, exclude: set[str] | None = None) -> set[Perm]:
    exclude = exclude or set()
    return {p for p in Perm if p.module in modules and p.action not in exclude}


SUPER_ADMIN = "SUPER_ADMIN"
ADMIN = "ADMIN"


@dataclass(frozen=True)
class SystemRole:
    name: str
    display_name: str
    description: str
    permissions: frozenset[str]


def _role(name: str, display_name: str, description: str, perms: set[Perm]) -> SystemRole:
    return SystemRole(name, display_name, description, frozenset(p.value for p in perms))


SYSTEM_ROLES: tuple[SystemRole, ...] = (
    _role(
        SUPER_ADMIN,
        "Super Administrator",
        "Full access. Passes every permission check.",
        set(Perm),
    ),
    _role(
        ADMIN,
        "Administrator",
        "All permissions, but cannot manage Super Administrators.",
        set(Perm),
    ),
    _role(
        "MANAGER",
        "Manager",
        "Views all business modules, approves transactions, sees reports and audit logs.",
        {p for p in Perm if p.module not in ADMIN_MODULES and p.action in ("view", "approve")}
        | {Perm.REPORTS_EXPORT, Perm.AUDIT_VIEW},
    ),
    _role(
        "ACCOUNTANT",
        "Accountant",
        "Finance, plus read-only customers, suppliers, sales and procurement.",
        _module("finance")
        | {
            Perm.CUSTOMERS_VIEW,
            Perm.SUPPLIERS_VIEW,
            Perm.SALES_VIEW,
            Perm.PROCUREMENT_VIEW,
            Perm.REPORTS_VIEW,
            Perm.REPORTS_EXPORT,
        }
        | _COMMON,
    ),
    _role(
        "HR_OFFICER",
        "HR Officer",
        "Employees (including salary) and leave approval.",
        _module("employees", "leave") | _COMMON,
    ),
    _role(
        "SALES_OFFICER",
        "Sales Officer",
        "Customers and sales, without delete or approve.",
        _module("customers", "sales", exclude={"delete", "approve"})
        | {Perm.PRODUCTS_VIEW}
        | _COMMON,
    ),
    _role(
        "PROCUREMENT_OFFICER",
        "Procurement Officer",
        "Suppliers and procurement, without approve.",
        _module("suppliers", "procurement", exclude={"approve"}) | {Perm.PRODUCTS_VIEW} | _COMMON,
    ),
    _role(
        "STOREKEEPER",
        "Storekeeper",
        "Products and inventory.",
        _module("products", "inventory") | _COMMON,
    ),
)

SYSTEM_ROLE_NAMES = frozenset(r.name for r in SYSTEM_ROLES)
