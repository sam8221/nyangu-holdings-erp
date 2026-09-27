"""Query helpers shared by every module: lookup-or-404, search, sort whitelists and pagination."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.orm import Session, lazyload

from app.schemas.common import PageParams
from app.utils.exceptions import BadRequestError, NotFoundError


def like_pattern(search: str) -> str:
    """Lower-cased LIKE pattern with %, _ and backslash escaped so they match literally."""
    escaped = search.lower().replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    return f"%{escaped}%"


def search_clause(search: str, *columns: Any) -> ColumnElement[bool]:
    pattern = like_pattern(search)
    return or_(*(func.lower(col).like(pattern, escape="\\") for col in columns))


def get_or_404[M](db: Session, model: type[M], obj_id: uuid.UUID | str, label: str) -> M:
    obj = db.get(model, obj_id)
    if obj is None:
        raise NotFoundError(f"{label} not found")
    return obj


def get_for_update_or_404[M](db: Session, model: type[M], obj_id: uuid.UUID, label: str) -> M:
    # Relationships load lazily here: eager-loaded related rows would otherwise be refreshed by
    # populate_existing, discarding unsaved changes made to them earlier in the request.
    stmt = (
        select(model)
        .options(lazyload("*"))
        .where(model.id == obj_id)  # type: ignore[attr-defined]
        .with_for_update(of=model)
        .execution_options(populate_existing=True)
    )
    obj = db.scalars(stmt).first()
    if obj is None:
        raise NotFoundError(f"{label} not found")
    return obj


def check_sort(params: PageParams, sort_fields: Mapping[str, Any]) -> None:
    if params.sort_by and params.sort_by not in sort_fields:
        allowed = ", ".join(sorted(sort_fields))
        raise BadRequestError(f"Invalid sort field '{params.sort_by}'. Allowed: {allowed}")


def paginate(
    db: Session,
    stmt: Select[Any],
    params: PageParams,
    sort_fields: Mapping[str, Any],
    default_sort: tuple[str, str],
    tiebreak: Any | None = None,
) -> tuple[list[Any], int]:
    """Apply sorting and paging. Returns (items, total). The sort field must be whitelisted."""
    check_sort(params, sort_fields)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0

    field = params.sort_by or default_sort[0]
    order = params.sort_order or (default_sort[1] if not params.sort_by else "asc")
    column = sort_fields[field]
    ordering = column.asc().nulls_last() if order == "asc" else column.desc().nulls_last()
    stmt = stmt.order_by(ordering)
    if tiebreak is not None:
        stmt = stmt.order_by(tiebreak)
    stmt = stmt.offset(params.offset).limit(params.page_size)
    return list(db.scalars(stmt).unique().all()), total
