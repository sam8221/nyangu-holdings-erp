"""Import every model here so Alembic autogenerate and relationship resolution can see them."""

from app.models.base import Base
from app.models.rbac import Permission, Role, role_permissions, user_roles
from app.models.system import AuditLog, DocumentSequence, Notification, PasswordResetToken
from app.models.token import RefreshToken, RevokedAccessToken
from app.models.user import User, UserStatus

__all__ = [
    "AuditLog",
    "Base",
    "DocumentSequence",
    "Notification",
    "PasswordResetToken",
    "Permission",
    "RefreshToken",
    "RevokedAccessToken",
    "Role",
    "User",
    "UserStatus",
    "role_permissions",
    "user_roles",
]
