"""Logging setup: request IDs on every line, and masking of anything that looks like a secret."""

from __future__ import annotations

import logging
import re
import sys
from contextvars import ContextVar

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

_SENSITIVE_KEYS = (
    r"(?:password|passwd|pwd|secret|token|access_token|refresh_token|api_key|authorization)"
)
_PATTERNS = [
    # key=value, key: value, "key": "value"
    re.compile(
        rf"(?i)(\"?{_SENSITIVE_KEYS}\w*\"?\s*[:=]\s*\"?)((?:bearer\s+)?[^\"\s,}}&]+)",
    ),
    # Authorization: Bearer <jwt>
    re.compile(r"(?i)(bearer\s+)([A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.?[A-Za-z0-9\-_.+/=]*)"),
    # Bare JWTs
    re.compile(r"()(eyJ[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_.+/=]*)"),
    # Argon2 hashes
    re.compile(r"()(\$argon2id?\$[^\s\"',]+)"),
]
MASK = "***"


def mask_sensitive(text: str) -> str:
    for pattern in _PATTERNS:
        text = pattern.sub(lambda m: m.group(1) + MASK, text)
    return text


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - never break logging
            return True
        masked = mask_sensitive(message)
        if masked != message:
            record.msg = masked
            record.args = None
        return True


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    handler.addFilter(RequestIdFilter())
    handler.addFilter(SensitiveDataFilter())

    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if not getattr(h, "_nyangu", False)]
    handler._nyangu = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level.upper())
    # SQL echo would leak parameters; keep the engine logger quiet unless explicitly wanted.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
