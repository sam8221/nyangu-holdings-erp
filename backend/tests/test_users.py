"""User management: create, validate, update, list/search/filter/sort, roles, status, resets."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import API, DEFAULT_PASSWORD, bearer, login, role_id

NEW_USER = {
    "full_name": "Mwila  Banda",
    "username": "MBanda",
    "email": "Mwila.Banda@NyanguHoldings.com",
    "phone": "+260 97 1234567",
    "password": "Welcome!2026x",
}


def _admin(auth_headers) -> dict[str, str]:
    return auth_headers("ADMIN", username="admin1")


# ------------------------------------------------------------------ create
def test_create_user(client: TestClient, auth_headers, db: Session) -> None:
    headers = _admin(auth_headers)
    body = {**NEW_USER, "role_ids": [role_id(db, "SALES_OFFICER")]}
    r = client.post(f"{API}/users", json=body, headers=headers)
    assert r.status_code == 201, r.text
    payload = r.json()
    assert payload["message"] == "User created successfully"
    data = payload["data"]
    assert data["full_name"] == "Mwila Banda"  # whitespace collapsed
    assert data["username"] == "mbanda" and data["email"] == "mwila.banda@nyanguholdings.com"
    assert data["status"] == "ACTIVE"
    assert [r["name"] for r in data["roles"]] == ["SALES_OFFICER"]
    assert "sales.create" in data["permissions"]
    assert "password" not in r.text.lower().replace("password_changed_at", "")
    # The new user can log in.
    assert login(client, "mbanda", NEW_USER["password"])["user"]["username"] == "mbanda"


def test_create_user_rejects_duplicate_email_and_username(client, auth_headers) -> None:
    headers = _admin(auth_headers)
    assert client.post(f"{API}/users", json=NEW_USER, headers=headers).status_code == 201

    dup_email = client.post(
        f"{API}/users", json={**NEW_USER, "username": "someoneelse"}, headers=headers
    )
    assert dup_email.status_code == 409
    assert dup_email.json()["errors"][0]["field"] == "email"

    dup_username = client.post(
        f"{API}/users", json={**NEW_USER, "email": "other@nyanguholdings.com"}, headers=headers
    )
    assert dup_username.status_code == 409
    assert dup_username.json()["errors"][0]["field"] == "username"


def test_create_user_validation(client, auth_headers) -> None:
    headers = _admin(auth_headers)
    r = client.post(
        f"{API}/users",
        json={
            "full_name": " ",
            "username": "a!",
            "email": "not-an-email",
            "phone": "call me",
            "password": "weak",
            "is_superuser": True,
        },
        headers=headers,
    )
    assert r.status_code == 422
    errors = {e["field"]: e["message"] for e in r.json()["errors"]}
    assert {"full_name", "username", "email", "phone", "password", "is_superuser"} <= set(errors)
    assert "uppercase letter" in errors["password"] and "symbol" in errors["password"]


def test_create_user_with_unknown_role(client, auth_headers) -> None:
    r = client.post(
        f"{API}/users",
        json={**NEW_USER, "role_ids": [str(uuid.uuid4())]},
        headers=_admin(auth_headers),
    )
    assert r.status_code == 400
    assert r.json()["errors"][0]["field"] == "role_ids"


# ------------------------------------------------------------------ read / update
def test_get_user_and_404(client, auth_headers, make_user) -> None:
    headers = _admin(auth_headers)
    user = make_user("HR_OFFICER")
    r = client.get(f"{API}/users/{user.id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["data"]["email"] == user.email
    assert "employees.view_salary" in r.json()["data"]["permissions"]

    missing = client.get(f"{API}/users/{uuid.uuid4()}", headers=headers)
    assert missing.status_code == 404 and missing.json()["error_code"] == "NOT_FOUND"
    assert client.get(f"{API}/users/not-a-uuid", headers=headers).status_code == 422


def test_update_user(client, auth_headers, make_user) -> None:
    headers = _admin(auth_headers)
    user = make_user()
    other = make_user()
    r = client.put(
        f"{API}/users/{user.id}",
        json={"full_name": "Chanda Mulenga", "phone": "0977000000"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["full_name"] == "Chanda Mulenga"
    assert r.json()["data"]["email"] == user.email  # untouched

    clash = client.put(f"{API}/users/{user.id}", json={"email": other.email}, headers=headers)
    assert clash.status_code == 409
    # Keeping your own email is not a clash.
    same = client.put(f"{API}/users/{user.id}", json={"email": user.email}, headers=headers)
    assert same.status_code == 200


# ------------------------------------------------------------------ list
def test_list_users_paginates(client, auth_headers, make_user) -> None:
    headers = _admin(auth_headers)
    for _ in range(4):
        make_user()
    r = client.get(f"{API}/users", params={"page": 2, "page_size": 2}, headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["meta"] == {"page": 2, "page_size": 2, "total": 5, "pages": 3}
    assert len(data["items"]) == 2


def test_list_users_search_filter_and_sort(client, auth_headers, make_user) -> None:
    headers = _admin(auth_headers)
    make_user("ACCOUNTANT", full_name="Mary Banda")
    make_user("ACCOUNTANT", full_name="Peter Banda", status="INACTIVE")
    make_user("STOREKEEPER", full_name="John Phiri")

    search = client.get(f"{API}/users", params={"search": "banda"}, headers=headers).json()
    assert {u["full_name"] for u in search["data"]["items"]} == {"Mary Banda", "Peter Banda"}

    filtered = client.get(
        f"{API}/users",
        params={"search": "banda", "status": "ACTIVE", "role": "accountant"},
        headers=headers,
    ).json()
    assert [u["full_name"] for u in filtered["data"]["items"]] == ["Mary Banda"]

    ordered = client.get(
        f"{API}/users", params={"sort_by": "full_name", "sort_order": "desc"}, headers=headers
    ).json()
    names = [u["full_name"] for u in ordered["data"]["items"]]
    assert names == sorted(names, reverse=True)


def test_list_users_search_treats_wildcards_literally(client, auth_headers, make_user) -> None:
    headers = _admin(auth_headers)
    make_user(full_name="Plain Name")
    r = client.get(f"{API}/users", params={"search": "%"}, headers=headers)
    assert r.json()["data"]["meta"]["total"] == 0


def test_list_users_rejects_bad_parameters(client, auth_headers) -> None:
    headers = _admin(auth_headers)
    bad_sort = client.get(f"{API}/users", params={"sort_by": "password_hash"}, headers=headers)
    assert bad_sort.status_code == 400
    assert "Invalid sort field" in bad_sort.json()["message"]
    assert client.get(f"{API}/users", params={"page_size": 101}, headers=headers).status_code == 422
    assert client.get(f"{API}/users", params={"page": 0}, headers=headers).status_code == 422
    assert client.get(f"{API}/users", params={"status": "GONE"}, headers=headers).status_code == 422


# ------------------------------------------------------------------ roles
def test_replace_user_roles(client, auth_headers, make_user, db: Session) -> None:
    headers = _admin(auth_headers)
    user = make_user("SALES_OFFICER")
    r = client.put(
        f"{API}/users/{user.id}/roles",
        json={"role_ids": [role_id(db, "ACCOUNTANT"), role_id(db, "STOREKEEPER")]},
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert [x["name"] for x in data["roles"]] == ["ACCOUNTANT", "STOREKEEPER"]
    assert "sales.create" not in data["permissions"]

    cleared = client.put(f"{API}/users/{user.id}/roles", json={"role_ids": []}, headers=headers)
    assert cleared.json()["data"]["roles"] == []


def test_user_cannot_change_own_roles(client, make_user, db: Session) -> None:
    admin = make_user("ADMIN")
    headers = bearer(login(client, admin.email)["access_token"])
    r = client.put(
        f"{API}/users/{admin.id}/roles",
        json={"role_ids": [role_id(db, "ACCOUNTANT")]},
        headers=headers,
    )
    assert r.status_code == 422
    assert r.json()["error_code"] == "BUSINESS_RULE_VIOLATION"


# ------------------------------------------------------------------ status
def test_deactivate_and_reactivate_user(client, auth_headers, make_user) -> None:
    headers = _admin(auth_headers)
    user = make_user("ACCOUNTANT")
    their_token = login(client, user.email)["access_token"]

    r = client.patch(f"{API}/users/{user.id}/status", json={"status": "INACTIVE"}, headers=headers)
    assert r.status_code == 200 and r.json()["data"]["status"] == "INACTIVE"
    assert r.json()["message"] == "User deactivated successfully"
    # Existing tokens stop working immediately and login is refused.
    assert client.get(f"{API}/auth/me", headers=bearer(their_token)).status_code == 401
    denied = client.post(
        f"{API}/auth/login", json={"identifier": user.email, "password": user.password}
    )
    assert denied.status_code == 403

    r = client.patch(f"{API}/users/{user.id}/status", json={"status": "ACTIVE"}, headers=headers)
    assert r.status_code == 200 and r.json()["data"]["status"] == "ACTIVE"
    assert login(client, user.email)["user"]["status"] == "ACTIVE"


def test_user_cannot_deactivate_self(client, make_user) -> None:
    admin = make_user("ADMIN")
    headers = bearer(login(client, admin.email)["access_token"])
    r = client.patch(f"{API}/users/{admin.id}/status", json={"status": "INACTIVE"}, headers=headers)
    assert r.status_code == 422
    assert "your own account" in r.json()["message"]


# ------------------------------------------------------------------ password reset
def test_admin_reset_password(client, auth_headers, make_user) -> None:
    headers = _admin(auth_headers)
    user = make_user()
    their_token = login(client, user.email)["access_token"]
    r = client.post(
        f"{API}/users/{user.id}/reset-password",
        json={"new_password": "Reset!Passw0rd"},
        headers=headers,
    )
    assert r.status_code == 200
    assert client.get(f"{API}/auth/me", headers=bearer(their_token)).status_code == 401
    old = client.post(
        f"{API}/auth/login", json={"identifier": user.email, "password": DEFAULT_PASSWORD}
    )
    assert old.status_code == 401
    assert login(client, user.email, "Reset!Passw0rd")["user"]["id"] == user.id


def test_admin_reset_password_validates_policy_and_self(client, make_user) -> None:
    admin = make_user("ADMIN")
    user = make_user()
    headers = bearer(login(client, admin.email)["access_token"])
    weak = client.post(
        f"{API}/users/{user.id}/reset-password", json={"new_password": "abc"}, headers=headers
    )
    assert weak.status_code == 422
    own = client.post(
        f"{API}/users/{admin.id}/reset-password",
        json={"new_password": "Reset!Passw0rd"},
        headers=headers,
    )
    assert own.status_code == 422
