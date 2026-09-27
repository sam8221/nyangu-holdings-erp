"""Document numbering, e.g. INV-2026-00001.

The counter row is incremented inside the caller's transaction, so numbers are gap-free (a rollback
also rolls back the increment) and concurrent requests are serialised on that row.
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.system import DocumentSequence
from app.utils.time import local_today


def next_number(db: Session, prefix: str, *, yearly: bool = True, width: int = 5) -> str:
    key = f"{prefix}-{local_today().year}" if yearly else prefix
    stmt = (
        insert(DocumentSequence)
        .values(name=key, last_value=1)
        .on_conflict_do_update(
            index_elements=[DocumentSequence.name],
            set_={"last_value": DocumentSequence.last_value + 1},
        )
        .returning(DocumentSequence.last_value)
    )
    value = db.execute(stmt).scalar_one()
    return f"{key}-{value:0{width}d}"
