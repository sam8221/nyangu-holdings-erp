"""Authentication: login, lockout, rate limiting, tokens, refresh rotation, logout, passwords."""

from __future__ import annotations

import uuid
from datetime import timedelta

import jwt
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.jwt import create_access_token
from app.config import get_settings
from app.models import User
from app.utils.time import utcnow
from tests.conftest import API, DEFAULT_PASSWORD, bearer, login

INVALID = "Invalid email/username or password"


def _post_login(client: TestClient, identifier: str, password: str):
    return client.post(f"{API}/auth/login", json={"identifier": identifier, "password": password})


# ------------------------------------------------------------------ login
def test_login_with_email_returns_tokens_and_user(client, make_user) -> None:
    user = make_user("ACCOUNTANT")
    r = _post_login(client, user.email, user.password)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True and body["message"] == "Login successful"
    data = body["data"]
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 3600 and data["refresh_expires_in"] == 7 * 24 * 3600
    assert data["user"]["email"] == user.email
    assert data["user"]["roles"][0]["name"] == "ACCOUNTANT"
    assert "finance.view" in data["user"]["permissions"]
    assert "password_hash" not in r.text


def test_login_with_username_is_case_insensitive(client, make_user) -> None:
    user = make_user(username="mbanda")
    assert _post_login(client, "MBanda", user.password).status_code == 200
    assert _post_login(client, user.email.upper(), user.password).status_code == 200


def test_wrong_password_and_unknown_user_look_the_same(client, make_user) -> None:
    user = make_user()
    wrong = _post_login(client, user.email, "Wrong!Passw0rd")
    unknown = _post_login(client, "ghost@nyanguholdings.com", "Wrong!Passw0rd")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["message"] == unknown.json()["message"] == INVALID
    assert wrong.json()["error_code"] == "UNAUTHENTICATED"


def test_password_is_stored_as_argon2id(client, make_user, db: Session) -> None:
    user = make_user()
    stored = db.get(User, uuid.UUID(user.id))
    assert stored.password_hash.startswith("$argon2id$")
    assert user.password not in stored.password_hash


def test_account_locks_after_repeated_failures(client, make_user, db: Session) -> None:
    user = make_user()
    for _ in range(get_settings().MAX_FAILED_LOGIN_ATTEMPTS):
        assert _post_login(client, user.email, "Wrong!Passw0rd").status_code == 401
    locked = _post_login(client, user.email, user.password)  # correct password, still locked
    assert locked.status_code == 401
    assert "locked" in locked.json()["message"].lower()

    # Once the lock expires the correct password works again.
    row = db.get(User, uuid.UUID(user.id))
    row.locked_until = utcnow() - timedelta(seconds=1)
    db.commit()
    assert _post_login(client, user.email, user.password).status_code == 200


def test_successful_login_resets_failure_counter(client, make_user, db: Session) -> None:
    user = make_user()
    for _ in range(3):
        _post_login(client, user.email, "Wrong!Passw0rd")
    assert _post_login(client, user.email, user.password).status_code == 200
    db.expire_all()
    row = db.get(User, uuid.UUID(user.id))
    assert row.failed_login_attempts == 0 and row.last_login_at is not None


def test_login_is_rate_limited_per_ip(client) -> None:
    limit = get_settings().LOGIN_RATE_LIMIT_PER_MINUTE
    for _ in range(limit):
        assert _post_login(client, "nobody@x.com", "Wrong!Passw0rd").status_code == 401
    r = _post_login(client, "nobody@x.com", "Wrong!Passw0rd")
    assert r.status_code == 429
    assert r.json()["error_code"] == "RATE_LIMITED"
    assert int(r.headers["Retry-After"]) > 0


def test_deactivated_user_cannot_log_in(client, make_user) -> None:
    user = make_user(status="INACTIVE")
    r = _post_login(client, user.email, user.password)
    assert r.status_code == 403
    assert "deactivated" in r.json()["message"]


# ------------------------------------------------------------------ access tokens
def test_me_returns_roles_and_permissions(client, make_user) -> None:
    user = make_user("STOREKEEPER")
    tokens = login(client, user.email)
    r = client.get(f"{API}/auth/me", headers=bearer(tokens["access_token"]))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["username"] == user.username
    assert [role["name"] for role in data["roles"]] == ["STOREKEEPER"]
    assert "inventory.adjust" in data["permissions"]
    assert data["is_super_admin"] is False


def test_missing_token_is_rejected(client) -> None:
    r = client.get(f"{API}/auth/me")
    assert r.status_code == 401
    assert r.json()["error_code"] == "UNAUTHENTICATED"
    assert r.headers["WWW-Authenticate"] == "Bearer"


def test_expired_token_is_rejected(client, make_user) -> None:
    user = make_user()
    s = get_settings()
    now = utcnow()
    token = jwt.encode(
        {
            "iss": s.JWT_ISSUER,
            "sub": user.id,
            "type": "access",
            "jti": "x",
            "tv": 1,
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        },
        s.SECRET_KEY,
        algorithm="HS256",
    )
    r = client.get(f"{API}/auth/me", headers=bearer(token))
    assert r.status_code == 401
    assert r.json()["message"] == "Token has expired"


def test_forged_token_is_rejected(client, make_user) -> None:
    user = make_user()
    s = get_settings()
    now = utcnow()
    token = jwt.encode(
        {
            "iss": s.JWT_ISSUER,
            "sub": user.id,
            "type": "access",
            "jti": "x",
            "tv": 1,
            "iat": now,
            "exp": now + timedelta(hours=1),
        },
        "a-completely-different-secret-key-0123456789",
        algorithm="HS256",
    )
    assert client.get(f"{API}/auth/me", headers=bearer(token)).status_code == 401


def test_alg_none_token_is_rejected(client, make_user) -> None:
    user = make_user()
    now = utcnow()
    token = jwt.encode(
        {
            "iss": get_settings().JWT_ISSUER,
            "sub": user.id,
            "type": "access",
            "jti": "x",
            "tv": 1,
            "iat": now,
            "exp": now + timedelta(hours=1),
        },
        key=None,
        algorithm="none",
    )
    assert client.get(f"{API}/auth/me", headers=bearer(token)).status_code == 401


def test_refresh_token_cannot_be_used_as_access_token(client, make_user) -> None:
    user = make_user()
    tokens = login(client, user.email)
    r = client.get(f"{API}/auth/me", headers=bearer(tokens["refresh_token"]))
    assert r.status_code == 401
    assert r.json()["message"] == "Invalid token type"


def test_token_with_stale_version_is_rejected(client, make_user) -> None:
    user = make_user()
    stale = create_access_token(uuid.UUID(user.id), token_version=0).token
    assert client.get(f"{API}/auth/me", headers=bearer(stale)).status_code == 401


# ------------------------------------------------------------------ refresh
def test_refresh_rotates_tokens(client, make_user) -> None:
    user = make_user()
    first = login(client, user.email)
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r.status_code == 200
    second = r.json()["data"]
    assert second["refresh_token"] != first["refresh_token"]
    assert client.get(f"{API}/auth/me", headers=bearer(second["access_token"])).status_code == 200
    # A new refresh token works once more.
    r2 = client.post(f"{API}/auth/refresh", json={"refresh_token": second["refresh_token"]})
    assert r2.status_code == 200


def test_refresh_token_reuse_revokes_every_session(client, make_user) -> None:
    user = make_user()
    first = login(client, user.email)
    second = client.post(
        f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]}
    ).json()["data"]

    reused = client.post(f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert reused.status_code == 401
    assert "already been used" in reused.json()["message"]
    # The legitimate (newer) tokens are dead too.
    assert client.get(f"{API}/auth/me", headers=bearer(second["access_token"])).status_code == 401
    assert (
        client.post(
            f"{API}/auth/refresh", json={"refresh_token": second["refresh_token"]}
        ).status_code
        == 401
    )


def test_access_token_cannot_be_used_to_refresh(client, make_user) -> None:
    user = make_user()
    tokens = login(client, user.email)
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert r.status_code == 401


# ------------------------------------------------------------------ logout
def test_logout_revokes_access_and_refresh_token(client, make_user) -> None:
    user = make_user()
    tokens = login(client, user.email)
    headers = bearer(tokens["access_token"])
    r = client.post(
        f"{API}/auth/logout", json={"refresh_token": tokens["refresh_token"]}, headers=headers
    )
    assert r.status_code == 200 and r.json()["message"] == "Logged out"
    assert client.get(f"{API}/auth/me", headers=headers).status_code == 401
    assert (
        client.post(
            f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).status_code
        == 401
    )


def test_logout_without_body_works(client, make_user) -> None:
    user = make_user()
    headers = bearer(login(client, user.email)["access_token"])
    assert client.post(f"{API}/auth/logout", headers=headers).status_code == 200
    assert client.get(f"{API}/auth/me", headers=headers).status_code == 401


def test_logout_all_devices_ends_other_sessions(client, make_user) -> None:
    user = make_user()
    laptop = login(client, user.email)
    phone = login(client, user.email)
    r = client.post(
        f"{API}/auth/logout", json={"all_devices": True}, headers=bearer(laptop["access_token"])
    )
    assert r.status_code == 200
    assert client.get(f"{API}/auth/me", headers=bearer(phone["access_token"])).status_code == 401
    assert (
        client.post(
            f"{API}/auth/refresh", json={"refresh_token": phone["refresh_token"]}
        ).status_code
        == 401
    )


# ------------------------------------------------------------------ change password
def test_change_password_rotates_sessions(client, make_user) -> None:
    user = make_user()
    current = login(client, user.email)
    other = login(client, user.email)
    new_password = "N3w!Password99"
    r = client.post(
        f"{API}/auth/change-password",
        json={"current_password": user.password, "new_password": new_password},
        headers=bearer(current["access_token"]),
    )
    assert r.status_code == 200
    fresh = r.json()["data"]
    assert client.get(f"{API}/auth/me", headers=bearer(fresh["access_token"])).status_code == 200
    assert client.get(f"{API}/auth/me", headers=bearer(other["access_token"])).status_code == 401
    assert client.get(f"{API}/auth/me", headers=bearer(current["access_token"])).status_code == 401
    assert _post_login(client, user.email, user.password).status_code == 401
    assert _post_login(client, user.email, new_password).status_code == 200


def test_change_password_requires_correct_current_password(client, make_user) -> None:
    user = make_user()
    headers = bearer(login(client, user.email)["access_token"])
    r = client.post(
        f"{API}/auth/change-password",
        json={"current_password": "Wrong!Passw0rd", "new_password": "N3w!Password99"},
        headers=headers,
    )
    assert r.status_code == 400
    assert r.json()["message"] == "Current password is incorrect"


def test_change_password_enforces_policy(client, make_user) -> None:
    user = make_user()
    headers = bearer(login(client, user.email)["access_token"])
    weak = client.post(
        f"{API}/auth/change-password",
        json={"current_password": user.password, "new_password": "password"},
        headers=headers,
    )
    assert weak.status_code == 422
    assert weak.json()["errors"][0]["field"] == "new_password"
    same = client.post(
        f"{API}/auth/change-password",
        json={"current_password": user.password, "new_password": DEFAULT_PASSWORD},
        headers=headers,
    )
    assert same.status_code == 422
    assert same.json()["error_code"] == "BUSINESS_RULE_VIOLATION"
