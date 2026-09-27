"""Import every model here so Alembic autogenerate and relationship resolution can see them."""

from app.models.base import Base
from app.models.hr import Employee, LeaveRequest
from app.models.organization import Branch, Company, Department, SystemSetting
from app.models.rbac import Permission, Role, role_permissions, user_roles
from app.models.system import AuditLog, DocumentSequence, Notification, PasswordResetToken
from app.models.token import RefreshToken, RevokedAccessToken
from app.models.user import User, UserStatus

__all__ = [
    "AuditLog",
    "Base",
    "Branch",
    "Company",
    "Department",
    "DocumentSequence",
    "Employee",
    "LeaveRequest",
    "Notification",
    "PasswordResetToken",
    "Permission",
    "RefreshToken",
    "RevokedAccessToken",
    "Role",
    "SystemSetting",
    "User",
    "UserStatus",
    "role_permissions",
    "user_roles",
]
