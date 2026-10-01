"""Tunable system settings. Defaults live here; the database stores only overrides."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.models.organization import SystemSetting
from app.schemas.organization import SettingsUpdate
from app.services.audit import AuditService, jsonable

DEFAULTS: dict[str, Any] = {
    "default_vat_rate": Decimal("16.00"),  # Zambia standard VAT rate
    "default_payment_terms_days": 30,
    "annual_leave_days": 24,  # 2 days per month, the Zambian statutory minimum
    "low_stock_alerts_enabled": True,
    "invoice_footer": "Thank you for your business.",
    # Unit prices on quotations and invoices include VAT unless a document says otherwise.
    "prices_include_tax": True,
    "quotation_validity_days": 30,
}
_DECIMAL_KEYS = {"default_vat_rate"}


def _decode(key: str, value: Any) -> Any:
    return Decimal(str(value)) if key in _DECIMAL_KEYS else value


class SettingsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def all(self) -> dict[str, Any]:
        stored = {s.key: s.value for s in self.db.scalars(select(SystemSetting)).all()}
        return {k: _decode(k, stored[k]) if k in stored else v for k, v in DEFAULTS.items()}

    def get(self, key: str) -> Any:
        row = self.db.get(SystemSetting, key)
        return _decode(key, row.value) if row else DEFAULTS[key]

    def update(self, ctx: AuthContext, data: SettingsUpdate) -> dict[str, Any]:
        before = self.all()
        for key, value in data.model_dump(exclude_unset=True).items():
            if value is None:
                continue
            row = self.db.get(SystemSetting, key)
            encoded = jsonable(value)
            if row is None:
                self.db.add(SystemSetting(key=key, value=encoded, updated_by_id=ctx.user.id))
            else:
                row.value = encoded
                row.updated_by_id = ctx.user.id
        self.db.flush()
        after = self.all()
        changes = {
            k: {"from": jsonable(before[k]), "to": jsonable(after[k])}
            for k in after
            if before[k] != after[k]
        }
        if changes:
            AuditService(self.db).log(
                "settings.update", actor=ctx.user, entity_type="settings", changes=changes
            )
        self.db.commit()
        return after
