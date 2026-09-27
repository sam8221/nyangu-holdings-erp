"""Outgoing email with pluggable backends (file, SMTP, console, memory)."""

from __future__ import annotations

import logging
import smtplib
import ssl
import uuid
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Protocol

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body: str


class EmailBackend(Protocol):
    def send(self, message: EmailMessage) -> None: ...


def _mime(message: EmailMessage) -> MimeMessage:
    s = get_settings()
    mime = MimeMessage()
    mime["From"] = s.EMAIL_FROM
    mime["To"] = message.to
    mime["Subject"] = message.subject
    mime["Date"] = formatdate(localtime=False)
    mime["Message-ID"] = make_msgid(domain="nyanguholdings.com")
    mime.set_content(message.body)
    return mime


class FileBackend:
    """Development: each email becomes an .eml file you can open in a mail client."""

    def send(self, message: EmailMessage) -> None:
        folder = Path(get_settings().EMAIL_FILE_DIR)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{uuid.uuid4().hex}.eml"
        path.write_bytes(bytes(_mime(message)))
        logger.info("Email '%s' written to %s", message.subject, path)


class ConsoleBackend:
    """Logs only the recipient and subject, never the body (it may contain links with tokens)."""

    def send(self, message: EmailMessage) -> None:
        logger.info("Email '%s' to %s (body not logged)", message.subject, message.to)


class MemoryBackend:
    def __init__(self) -> None:
        self.outbox: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.outbox.append(message)


class SmtpBackend:
    def send(self, message: EmailMessage) -> None:
        s = get_settings()
        assert s.SMTP_HOST
        context = ssl.create_default_context()
        with smtplib.SMTP(s.SMTP_HOST, s.SMTP_PORT, timeout=s.SMTP_TIMEOUT_SECONDS) as smtp:
            if s.SMTP_USE_TLS:
                smtp.starttls(context=context)
            if s.SMTP_USERNAME and s.SMTP_PASSWORD:
                smtp.login(s.SMTP_USERNAME, s.SMTP_PASSWORD)
            smtp.send_message(_mime(message))


_memory_backend = MemoryBackend()


def get_email_backend() -> EmailBackend:
    kind = get_settings().EMAIL_BACKEND
    if kind == "smtp":
        return SmtpBackend()
    if kind == "console":
        return ConsoleBackend()
    if kind == "memory":
        return _memory_backend
    return FileBackend()


def memory_outbox() -> list[EmailMessage]:
    return _memory_backend.outbox


def send_email(message: EmailMessage) -> None:
    """Send, logging (not raising) on failure. Called from background tasks."""
    try:
        get_email_backend().send(message)
    except Exception:  # noqa: BLE001 - delivery problems must not break the request
        logger.exception("Failed to send email '%s'", message.subject)
