"""RBAC enforcement: forbidden access, view-only users, Super Admin protection, escalation."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.permissions import SYSTEM_ROLES
from tests.conftest import API, bearer, login, role_id

NEW_USER = {
    "full_name": "New Person",
    "username": "newperson",
    "email": "new.person@nyanguholdings.com",
    "password": "Welcome!2026x",
}


def test_role_without_permission_is_forbidden(client: TestClient, auth_headers) -> None:
    headers = auth_headers("SALES_OFFICER")
    for method, path in [
        ("get", "/users"),
        ("post", "/users"),
        ("get", "/roles"),
        ("get", "/permissions"),
    ]:
        r = client.request(method, f"{API}{path}", headers=headers, json=NEW_USER)
        assert r.status_code == 403, (method, path)
        assert r.json()["error_code"] == "FORBIDDEN"


def test_user_without_roles_has_no_access(client, auth_headers) -> None:
    headers = auth_headers()
    assert client.get(f"{API}/auth/me", headers=headers).json()["data"]["permissions"] == []
    assert client.get(f"{API}/users", headers=headers).status_code == 403


def test_view_only_user_cannot_modify(client, auth_headers, make_user, db: Session) -> None:
    viewer_role = client.post(
        f"{API}/roles",
        json={"name": "USER_VIEWER", "display_name": "User viewer", "permissions": ["users.view"]},
        headers=auth_headers("SUPER_ADMIN", username="root"),
    ).json()["data"]
    viewer = make_user()
    client.put(
        f"{API}/users/{viewer.id}/roles",
        json={"role_ids": [viewer_role["id"]]},
        headers=auth_headers("SUPER_ADMIN", username="root2"),
    )
    headers = bearer(login(client, viewer.email)["access_token"])
    target = make_user()

    assert client.get(f"{API}/users", headers=headers).status_code == 200
    assert client.get(f"{API}/users/{target.id}", headers=headers).status_code == 200
    assert client.post(f"{API}/users", json=NEW_USER, headers=headers).status_code == 403
    assert (
        client.put(
            f"{API}/users/{target.id}", json={"full_name": "X Y"}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"{API}/users/{target.id}/status", json={"status": "INACTIVE"}, headers=headers
        ).status_code
        == 403
    )


def test_role_changes_apply_without_new_login(client, auth_headers, make_user, db: Session) -> None:
    admin_headers = auth_headers("ADMIN", username="admin1")
    user = make_user()
    headers = bearer(login(client, user.email)["access_token"])
    assert client.get(f"{API}/permissions", headers=headers).status_code == 403

    client.put(
        f"{API}/users/{user.id}/roles",
        json={"role_ids": [role_id(db, "ADMIN")]},
        headers=admin_headers,
    )
    assert client.get(f"{API}/permissions", headers=headers).status_code == 200  # same token


def test_deactivated_role_grants_nothing(client, auth_headers, make_user) -> None:
    root = auth_headers("SUPER_ADMIN", username="root")
    role = client.post(
        f"{API}/roles",
        json={"name": "AUDITOR", "display_name": "Auditor", "permissions": ["users.view"]},
        headers=root,
    ).json()["data"]
    user = make_user()
    client.put(f"{API}/users/{user.id}/roles", json={"role_ids": [role["id"]]}, headers=root)
    headers = bearer(login(client, user.email)["access_token"])
    assert client.get(f"{API}/users", headers=headers).status_code == 200

    client.put(f"{API}/roles/{role['id']}", json={"is_active": False}, headers=root)
    assert client.get(f"{API}/users", headers=headers).status_code == 403


def test_create_with_roles_requires_assign_roles(client, auth_headers, db: Session) -> None:
    creator_role = client.post(
        f"{API}/roles",
        json={
            "name": "USER_CREATOR",
            "display_name": "User creator",
            "permissions": ["users.create", "users.view"],
        },
        headers=auth_headers("SUPER_ADMIN", username="root"),
    ).json()["data"]
    headers = auth_headers(creator_role["name"], username="creator")

    with_roles = {**NEW_USER, "role_ids": [role_id(db, "STOREKEEPER")]}
    r = client.post(f"{API}/users", json=with_roles, headers=headers)
    assert r.status_code == 403
    assert "users.assign_roles" in r.json()["message"]
    assert client.post(f"{API}/users", json=NEW_USER, headers=headers).status_code == 201


# ------------------------------------------------------------------ Super Admin protection
def test_admin_cannot_create_or_grant_super_admin(client, auth_headers, make_user, db) -> None:
    headers = auth_headers("ADMIN", username="admin1")
    sa_role = role_id(db, "SUPER_ADMIN")
    r = client.post(f"{API}/users", json={**NEW_USER, "role_ids": [sa_role]}, headers=headers)
    assert r.status_code == 403

    target = make_user()
    r = client.put(f"{API}/users/{target.id}/roles", json={"role_ids": [sa_role]}, headers=headers)
    assert r.status_code == 403


def test_admin_cannot_manage_a_super_admin(client, auth_headers, make_user, db) -> None:
    headers = auth_headers("ADMIN", username="admin1")
    boss = make_user("SUPER_ADMIN")
    calls = [
        ("put", f"/users/{boss.id}", {"full_name": "Changed Name"}),
        ("patch", f"/users/{boss.id}/status", {"status": "INACTIVE"}),
        ("put", f"/users/{boss.id}/roles", {"role_ids": [role_id(db, "ACCOUNTANT")]}),
        ("post", f"/users/{boss.id}/reset-password", {"new_password": "Hacked!Passw0rd"}),
    ]
    for method, path, body in calls:
        r = client.request(method, f"{API}{path}", json=body, headers=headers)
        assert r.status_code == 403, (method, path, r.text)
    # Reading is still allowed.
    assert client.get(f"{API}/users/{boss.id}", headers=headers).status_code == 200


def test_super_admin_can_manage_another_super_admin(client, make_user) -> None:
    first = make_user("SUPER_ADMIN")
    second = make_user("SUPER_ADMIN")
    headers = bearer(login(client, first.email)["access_token"])
    r = client.patch(
        f"{API}/users/{second.id}/status", json={"status": "INACTIVE"}, headers=headers
    )
    assert r.status_code == 200


def test_super_admin_passes_every_permission_check(client, auth_headers) -> None:
    headers = auth_headers("SUPER_ADMIN", username="root")
    me = client.get(f"{API}/auth/me", headers=headers).json()["data"]
    assert me["is_super_admin"] is True
    for path in ("/users", "/roles", "/permissions"):
        assert client.get(f"{API}{path}", headers=headers).status_code == 200


def test_last_active_super_admin_is_protected(db: Session, make_user) -> None:
    """Defence in depth: the service refuses to remove the last active SUPER_ADMIN."""
    import uuid as _uuid

    import pytest

    from app.auth.dependencies import AuthContext
    from app.auth.jwt import TokenPayload
    from app.models import User
    from app.services.user_service import UserService
    from app.utils.exceptions import BusinessRuleError
    from app.utils.time import utcnow

    only = make_user("SUPER_ADMIN")
    actor = make_user("SUPER_ADMIN", status="INACTIVE")  # an inactive SA does not count
    actor_row = db.get(User, _uuid.UUID(actor.id))
    ctx = AuthContext(
        user=actor_row,
        token=TokenPayload(actor_row.id, "jti", "access", 1, utcnow()),
        permissions=frozenset(),
        roles=frozenset({"SUPER_ADMIN"}),
    )
    with pytest.raises(BusinessRuleError, match="At least one active Super Administrator"):
        UserService(db).set_status(ctx, _uuid.UUID(only.id), "INACTIVE")
    db.rollback()
    with pytest.raises(BusinessRuleError, match="At least one active Super Administrator"):
        UserService(db).set_roles(ctx, _uuid.UUID(only.id), [])


# ------------------------------------------------------------------ privilege escalation
def test_cannot_create_role_with_permissions_you_lack(client, auth_headers) -> None:
    root = auth_headers("SUPER_ADMIN", username="root")
    client.post(
        f"{API}/roles",
        json={
            "name": "ROLE_MANAGER",
            "display_name": "Role manager",
            "permissions": ["roles.view", "roles.create", "roles.update", "users.view"],
        },
        headers=root,
    )
    headers = auth_headers("ROLE_MANAGER", username="rm")
    r = client.post(
        f"{API}/roles",
        json={"name": "SNEAKY", "display_name": "Sneaky", "permissions": ["finance.approve"]},
        headers=headers,
    )
    assert r.status_code == 403
    assert "finance.approve" in r.json()["message"]

    allowed = client.post(
        f"{API}/roles",
        json={"name": "VIEWER", "display_name": "Viewer", "permissions": ["users.view"]},
        headers=headers,
    )
    assert allowed.status_code == 201
    # Adding a permission they lack to an existing role is also refused.
    r = client.put(
        f"{API}/roles/{allowed.json()['data']['id']}",
        json={"permissions": ["users.view", "users.create"]},
        headers=headers,
    )
    assert r.status_code == 403


def test_cannot_assign_role_with_more_permissions_than_you_have(
    client, auth_headers, make_user, db: Session
) -> None:
    root = auth_headers("SUPER_ADMIN", username="root")
    client.post(
        f"{API}/roles",
        json={
            "name": "HR_ADMIN",
            "display_name": "HR admin",
            "permissions": ["users.view", "users.assign_roles", "employees.view"],
        },
        headers=root,
    )
    headers = auth_headers("HR_ADMIN", username="hradmin")
    target = make_user()
    r = client.put(
        f"{API}/users/{target.id}/roles",
        json={"role_ids": [role_id(db, "ACCOUNTANT")]},
        headers=headers,
    )
    assert r.status_code == 403
    assert "ACCOUNTANT" in r.json()["message"]


def test_system_roles_have_expected_defaults() -> None:
    by_name = {r.name: r.permissions for r in SYSTEM_ROLES}
    assert len(by_name) == 8
    assert "sales.delete" not in by_name["SALES_OFFICER"]
    assert "sales.approve" not in by_name["SALES_OFFICER"]
    assert "procurement.approve" not in by_name["PROCUREMENT_OFFICER"]
    assert "employees.view_salary" in by_name["HR_OFFICER"]
    assert "leave.approve" in by_name["HR_OFFICER"]
    assert {"finance.approve", "customers.view"} <= by_name["ACCOUNTANT"]
    assert "customers.create" not in by_name["ACCOUNTANT"]
    assert {"sales.approve", "audit.view", "reports.view"} <= by_name["MANAGER"]
    assert "users.create" not in by_name["MANAGER"]
