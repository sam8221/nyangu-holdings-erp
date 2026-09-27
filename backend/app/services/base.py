"""Small helpers shared by the module services."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.utils.exceptions import BadRequestError, BusinessRuleError, ConflictError, NotFoundError


def apply_changes(obj: Any, changes: dict[str, Any], required: Iterable[str] = ()) -> None:
    """Copy ``changes`` onto ``obj``; fields in ``required`` may not be set to null."""
    for field in required:
        if field in changes and changes[field] is None:
            raise BadRequestError(
                f"{field} cannot be null", errors=[{"field": field, "message": "Required"}]
            )
    for key, value in changes.items():
        setattr(obj, key, value)


def ensure_unique(
    db: Session,
    model: type,
    field: str,
    value: Any,
    *,
    exclude_id: uuid.UUID | None = None,
    label: str | None = None,
) -> None:
    if value is None:
        return
    column = getattr(model, field)
    stmt = select(model.id).where(column == value)  # type: ignore[attr-defined]
    if exclude_id is not None:
        stmt = stmt.where(model.id != exclude_id)  # type: ignore[attr-defined]
    if db.scalar(stmt) is not None:
        name = label or field.replace("_", " ")
        raise ConflictError(
            f"{name[0].upper() + name[1:]} is already in use",
            errors=[{"field": field, "message": f"{name} is already in use"}],
        )


def require_exists(db: Session, model: type, obj_id: uuid.UUID | None, field: str) -> Any:
    """Load a referenced record or fail with a field-level 400."""
    if obj_id is None:
        return None
    obj = db.get(model, obj_id)
    if obj is None:
        raise BadRequestError(
            f"{field} refers to a record that does not exist",
            errors=[{"field": field, "message": "Not found"}],
        )
    return obj


def require_active(obj: Any, field: str) -> None:
    if obj is not None and getattr(obj, "is_active", True) is False:
        raise BusinessRuleError(
            f"{field} refers to an inactive record",
            errors=[{"field": field, "message": "Inactive"}],
        )


def delete_or_block(
    db: Session, obj: Any, label: str, after: Callable[[], None] | None = None
) -> None:
    """Delete ``obj``; if other records still reference it, refuse with a helpful message."""
    try:
        with db.begin_nested():
            db.delete(obj)
            db.flush()
    except IntegrityError as exc:
        raise BusinessRuleError(
            f"This {label} is used by other records and cannot be deleted. Deactivate it instead."
        ) from exc
    if after:
        after()


def not_found(label: str) -> NotFoundError:
    return NotFoundError(f"{label} not found")
