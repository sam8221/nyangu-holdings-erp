"""Audit trail. Entries are written in the same transaction as the change they describe."""

from __future__ import annotations

import enum
import uuid
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import User
from app.models.system import AuditLog
from app.utils.logging import client_ip_ctx, request_id_ctx, user_agent_ctx

# Never copied into the audit log, even when listed by a caller.
_SENSITIVE_FIELDS = {"password", "password_hash", "token", "token_hash", "secret"}


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (uuid.UUID,)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [jsonable(v) for v in value]
    return str(value)


def snapshot(obj: Any, fields: Iterable[str]) -> dict[str, Any]:
    return {f: jsonable(getattr(obj, f, None)) for f in fields if f not in _SENSITIVE_FIELDS}


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Only the fields that changed, as {field: {"from": old, "to": new}}."""
    keys = [k for k in {**before, **after} if k not in _SENSITIVE_FIELDS]
    return {
        k: {"from": before.get(k), "to": after.get(k)}
        for k in keys
        if before.get(k) != after.get(k)
    }


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def log(
        self,
        action: str,
        *,
        actor: User | None,
        entity_type: str | None = None,
        entity_id: Any = None,
        summary: str | None = None,
        changes: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            actor_id=actor.id if actor else None,
            actor_label=actor.email if actor else None,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            summary=summary[:500] if summary else None,
            changes=jsonable(changes) if changes else None,
            ip_address=client_ip_ctx.get(),
            user_agent=user_agent_ctx.get(),
            request_id=request_id_ctx.get() if request_id_ctx.get() != "-" else None,
        )
        self.db.add(entry)
        return entry
