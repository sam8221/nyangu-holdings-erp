"""Forgotten-password flow: email link, single use, expiry, no account enumeration."""

from __future__ import annotations

import re
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.system import AuditLog, PasswordResetToken
from app.services.email import memory_outbox
from app.utils.time import utcnow
from tests.conftest import API, bearer, login

NEW_PASSWORD = "Brand!New2026x"


def _request(client, email: str):
    return client.post(f"{API}/auth/forgot-password", json={"email": email})


def _token_from_outbox() -> str:
    assert memory_outbox(), "no email was sent"
    match = re.search(r"reset-password\?token=([A-Za-z0-9_\-]+)", memory_outbox()[-1].body)
    assert match
    return match.group(1)


def test_forgot_password_emails_a_link(client, make_user) -> None:
    user = make_user(full_name="Mutale Zulu")
    r = _request(client, user.email.upper())
    assert r.status_code == 200
    assert len(memory_outbox()) == 1
    mail = memory_outbox()[0]
    assert mail.to == user.email
    assert "Mutale Zulu" in mail.body
    assert "https://erp.example.com/reset-password?token=" in mail.body


def test_forgot_password_does_not_reveal_accounts(client, make_user) -> None:
    active = make_user()
    inactive = make_user(status="INACTIVE")
    known = _request(client, active.email)
    unknown = _request(client, "nobody@nyanguholdings.com")
    disabled = _request(client, inactive.email)
    assert known.status_code == unknown.status_code == disabled.status_code == 200
    assert known.json() == unknown.json() == disabled.json()
    assert len(memory_outbox()) == 1  # only the active account got an email


def test_reset_password_with_token(client, make_user, db: Session) -> None:
    user = make_user()
    session = login(client, user.email)
    _request(client, user.email)
    token = _token_from_outbox()

    r = client.post(
        f"{API}/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert r.status_code == 200
    # Old sessions end, old password fails, new password works.
    assert client.get(f"{API}/auth/me", headers=bearer(session["access_token"])).status_code == 401
    old = client.post(
        f"{API}/auth/login", json={"identifier": user.email, "password": user.password}
    )
    assert old.status_code == 401
    assert login(client, user.email, NEW_PASSWORD)["user"]["id"] == user.id
    # Only a hash of the token is stored.
    stored = db.scalars(select(PasswordResetToken)).one()
    assert stored.token_hash != token and len(stored.token_hash) == 64


def test_reset_token_is_single_use(client, make_user) -> None:
    user = make_user()
    _request(client, user.email)
    token = _token_from_outbox()
    body = {"token": token, "new_password": NEW_PASSWORD}
    assert client.post(f"{API}/auth/reset-password", json=body).status_code == 200
    again = client.post(
        f"{API}/auth/reset-password", json={**body, "new_password": "Another!2026x"}
    )
    assert again.status_code == 400
    assert "invalid or has expired" in again.json()["message"]


def test_newer_request_invalidates_older_link(client, make_user) -> None:
    user = make_user()
    _request(client, user.email)
    first = _token_from_outbox()
    _request(client, user.email)
    second = _token_from_outbox()
    assert first != second
    stale = client.post(
        f"{API}/auth/reset-password", json={"token": first, "new_password": NEW_PASSWORD}
    )
    assert stale.status_code == 400
    fresh = client.post(
        f"{API}/auth/reset-password", json={"token": second, "new_password": NEW_PASSWORD}
    )
    assert fresh.status_code == 200


def test_expired_reset_token_is_rejected(client, make_user, db: Session) -> None:
    user = make_user()
    _request(client, user.email)
    token = _token_from_outbox()
    stored = db.scalars(select(PasswordResetToken)).one()
    stored.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    r = client.post(
        f"{API}/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert r.status_code == 400


def test_reset_password_validates_input(client) -> None:
    weak = client.post(
        f"{API}/auth/reset-password", json={"token": "x" * 43, "new_password": "weak"}
    )
    assert weak.status_code == 422
    bogus = client.post(
        f"{API}/auth/reset-password", json={"token": "x" * 43, "new_password": NEW_PASSWORD}
    )
    assert bogus.status_code == 400


def test_reset_clears_lockout_and_is_audited(client, make_user, db: Session) -> None:
    user = make_user()
    for _ in range(get_settings().MAX_FAILED_LOGIN_ATTEMPTS):
        client.post(f"{API}/auth/login", json={"identifier": user.email, "password": "Bad!Pass1x"})
    _request(client, user.email)
    client.post(
        f"{API}/auth/reset-password",
        json={"token": _token_from_outbox(), "new_password": NEW_PASSWORD},
    )
    assert login(client, user.email, NEW_PASSWORD)
    actions = set(
        db.scalars(select(AuditLog.action).where(AuditLog.actor_id == uuid.UUID(user.id))).all()
    )
    assert {
        "auth.account_locked",
        "auth.password_reset_requested",
        "auth.password_reset",
    } <= actions


def test_forgot_password_is_rate_limited(client) -> None:
    limit = get_settings().PASSWORD_RESET_RATE_LIMIT_PER_HOUR
    for _ in range(limit):
        assert _request(client, "someone@nyanguholdings.com").status_code == 200
    r = _request(client, "someone@nyanguholdings.com")
    assert r.status_code == 429
