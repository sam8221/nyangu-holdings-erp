"""Generic create/read/update/delete for reference ("master") data such as customers.

Subclasses declare the model, labels, unique fields, sort whitelist and search columns; hooks
let them validate references or set defaults. Every change is audited.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any, ClassVar

from pydantic import BaseModel
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.repositories.query import get_or_404, paginate, search_clause
from app.schemas.common import Page, PageParams
from app.services.audit import AuditService, diff, snapshot
from app.services.base import apply_changes, delete_or_block, ensure_unique
from app.utils.sequences import next_number


class MasterDataService:
    model: ClassVar[type]
    label: ClassVar[str]  # "Customer"
    entity_type: ClassVar[str]  # "customer"
    action_prefix: ClassVar[str]  # "customers"
    number_field: ClassVar[str | None] = None  # generated code column, e.g. "code"
    number_prefix: ClassVar[str | None] = None  # e.g. "CUS"
    unique_fields: ClassVar[Mapping[str, str]] = {}  # field -> human label
    required_fields: ClassVar[tuple[str, ...]] = ()
    sort_fields: ClassVar[Mapping[str, Any]] = {}
    default_sort: ClassVar[tuple[str, str]] = ("created_at", "desc")
    search_columns: ClassVar[tuple[Any, ...]] = ()
    audited_fields: ClassVar[tuple[str, ...]] = ()

    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    # ------------------------------------------------------------------ hooks
    def validate(self, values: dict[str, Any], existing: Any | None) -> None:
        """Check references and business rules. ``values`` holds only the fields being set."""

    def defaults(self, values: dict[str, Any]) -> dict[str, Any]:
        return values

    def describe(self, obj: Any) -> str:
        return getattr(obj, "name", str(obj.id))

    def filter(self, stmt: Select[Any], filters: Mapping[str, Any]) -> Select[Any]:
        for field, value in filters.items():
            if value is not None:
                stmt = stmt.where(getattr(self.model, field) == value)
        return stmt

    # ------------------------------------------------------------------ queries
    def list(self, params: PageParams, **filters: Any) -> dict[str, Any]:
        stmt = self.filter(select(self.model), filters)
        if params.search and self.search_columns:
            stmt = stmt.where(search_clause(params.search, *self.search_columns))
        items, total = paginate(
            self.db, stmt, params, self.sort_fields, self.default_sort, self.model.id
        )
        return Page.build(items, total, params).model_dump()

    def get(self, obj_id: uuid.UUID) -> Any:
        return get_or_404(self.db, self.model, obj_id, self.label)

    # ------------------------------------------------------------------ commands
    def _check_unique(self, values: dict[str, Any], exclude_id: uuid.UUID | None) -> None:
        for field, label in self.unique_fields.items():
            if field in values:
                ensure_unique(
                    self.db, self.model, field, values[field], exclude_id=exclude_id, label=label
                )

    def _next_free_number(self) -> str:
        """Next automatic code, skipping any that were typed in by hand (e.g. "ITM-00007")."""
        column = getattr(self.model, self.number_field)  # type: ignore[arg-type]
        while True:
            candidate = next_number(self.db, self.number_prefix, yearly=False)  # type: ignore[arg-type]
            if self.db.scalar(select(self.model.id).where(column == candidate)) is None:
                return candidate

    def create(self, ctx: AuthContext, data: BaseModel) -> Any:
        values = self.defaults(data.model_dump())
        self._check_unique(values, None)
        self.validate(values, None)
        if self.number_field and self.number_prefix and not values.get(self.number_field):
            values[self.number_field] = self._next_free_number()
        obj = self.model(**values)
        self.db.add(obj)
        self.db.flush()
        self.audit.log(
            f"{self.action_prefix}.create",
            actor=ctx.user,
            entity_type=self.entity_type,
            entity_id=obj.id,
            summary=f"Created {self.label.lower()} {self.describe(obj)}",
            changes=snapshot(obj, self.audited_fields),
        )
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update(self, ctx: AuthContext, obj_id: uuid.UUID, data: BaseModel) -> Any:
        obj = self.get(obj_id)
        changes = data.model_dump(exclude_unset=True)
        self._check_unique(changes, obj.id)
        self.validate(changes, obj)
        before = snapshot(obj, self.audited_fields)
        apply_changes(obj, changes, required=self.required_fields)
        delta = diff(before, snapshot(obj, self.audited_fields))
        if delta:
            self.audit.log(
                f"{self.action_prefix}.update",
                actor=ctx.user,
                entity_type=self.entity_type,
                entity_id=obj.id,
                summary=f"Updated {self.label.lower()} {self.describe(obj)}",
                changes=delta,
            )
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete(self, ctx: AuthContext, obj_id: uuid.UUID) -> None:
        obj = self.get(obj_id)
        description = self.describe(obj)
        delete_or_block(self.db, obj, self.label.lower())
        self.audit.log(
            f"{self.action_prefix}.delete",
            actor=ctx.user,
            entity_type=self.entity_type,
            entity_id=obj_id,
            summary=f"Deleted {self.label.lower()} {description}",
        )
        self.db.commit()
