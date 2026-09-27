"""Roles and permissions endpoints, and the seed script."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Permission, Role, User
from app.seed.catalog import seed_catalog
from app.seed.run import seed_admin
from tests.conftest import API, role_id


def test_list_roles_with_permissions_and_user_counts(
    client: TestClient, auth_headers, make_user
) -> None:
    headers = auth_headers("ADMIN", username="admin1")
    make_user("ACCOUNTANT")
    make_user("ACCOUNTANT")
    r = client.get(f"{API}/roles", headers=headers)
    assert r.status_code == 200
    roles = {role["name"]: role for role in r.json()["data"]}
    assert len(roles) == 8
    assert roles["ACCOUNTANT"]["user_count"] == 2
    assert roles["ADMIN"]["user_count"] == 1
    assert roles["SUPER_ADMIN"]["is_system"] is True
    assert "finance.view" in roles["ACCOUNTANT"]["permissions"]


def test_custom_role_lifecycle(client, auth_headers) -> None:
    headers = auth_headers("ADMIN", username="admin1")
    created = client.post(
        f"{API}/roles",
        json={
            "name": "warehouse_supervisor",
            "display_name": "Warehouse Supervisor",
            "description": "Runs the Lusaka warehouse",
            "permissions": ["inventory.view", "INVENTORY.ADJUST", "inventory.view"],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    role = created.json()["data"]
    assert role["name"] == "WAREHOUSE_SUPERVISOR"
    assert role["permissions"] == ["inventory.adjust", "inventory.view"]
    assert role["is_system"] is False and role["user_count"] == 0

    assert client.get(f"{API}/roles/{role['id']}", headers=headers).status_code == 200

    updated = client.put(
        f"{API}/roles/{role['id']}",
        json={"display_name": "Stores Supervisor", "permissions": ["inventory.view"]},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["display_name"] == "Stores Supervisor"
    assert updated.json()["data"]["permissions"] == ["inventory.view"]

    deleted = client.delete(f"{API}/roles/{role['id']}", headers=headers)
    assert deleted.status_code == 200
    assert client.get(f"{API}/roles/{role['id']}", headers=headers).status_code == 404


def test_role_validation_and_conflicts(client, auth_headers) -> None:
    headers = auth_headers("ADMIN", username="admin1")
    dup = client.post(
        f"{API}/roles", json={"name": "ACCOUNTANT", "display_name": "Again"}, headers=headers
    )
    assert dup.status_code == 409
    unknown = client.post(
        f"{API}/roles",
        json={"name": "NEW_ROLE", "display_name": "New", "permissions": ["rockets.launch"]},
        headers=headers,
    )
    assert unknown.status_code == 400
    assert "rockets.launch" in unknown.json()["errors"][0]["message"]
    bad_name = client.post(
        f"{API}/roles", json={"name": "1 bad name", "display_name": "Bad"}, headers=headers
    )
    assert bad_name.status_code == 422


def test_system_role_protection(client, auth_headers, db: Session) -> None:
    headers = auth_headers("SUPER_ADMIN", username="root")
    sa = role_id(db, "SUPER_ADMIN")
    accountant = role_id(db, "ACCOUNTANT")

    r = client.put(f"{API}/roles/{sa}", json={"display_name": "Boss"}, headers=headers)
    assert r.status_code == 422 and "SUPER_ADMIN" in r.json()["message"]
    assert client.delete(f"{API}/roles/{accountant}", headers=headers).status_code == 422
    assert (
        client.put(
            f"{API}/roles/{accountant}", json={"is_active": False}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"{API}/roles/{accountant}", json={"name": "BOOKKEEPER"}, headers=headers
        ).status_code
        == 422
    )
    # Editing a system role's permissions is allowed.
    ok = client.put(
        f"{API}/roles/{accountant}",
        json={"permissions": ["finance.view", "reports.view"]},
        headers=headers,
    )
    assert ok.status_code == 200 and ok.json()["data"]["permissions"] == [
        "finance.view",
        "reports.view",
    ]


def test_role_assigned_to_users_cannot_be_deleted(client, auth_headers, make_user) -> None:
    headers = auth_headers("ADMIN", username="admin1")
    role = client.post(
        f"{API}/roles", json={"name": "TEMP_ROLE", "display_name": "Temp"}, headers=headers
    ).json()["data"]
    user = make_user()
    client.put(f"{API}/users/{user.id}/roles", json={"role_ids": [role["id"]]}, headers=headers)
    r = client.delete(f"{API}/roles/{role['id']}", headers=headers)
    assert r.status_code == 422
    assert "assigned to 1 user" in r.json()["message"]


def test_permission_catalogue(client, auth_headers) -> None:
    headers = auth_headers("ADMIN", username="admin1")
    everything = client.get(f"{API}/permissions", headers=headers).json()["data"]
    assert len(everything) == 60
    users_only = client.get(f"{API}/permissions", params={"module": "users"}, headers=headers)
    codes = [p["code"] for p in users_only.json()["data"]]
    assert codes == sorted(
        ["users.view", "users.create", "users.update", "users.assign_roles", "users.reset_password"]
    )


def test_seed_is_idempotent_and_creates_admin(db: Session) -> None:
    # The fixture already seeded once; seeding again must not duplicate anything.
    again = seed_catalog(db)
    assert (again.permissions_created, again.roles_created) == (0, 0)
    assert db.scalar(select(func.count()).select_from(Permission)) == 60
    assert db.scalar(select(func.count()).select_from(Role)) == 8

    user, created = seed_admin(db, "Admin@NyanguHoldings.com", "First!Admin2026")
    db.commit()
    assert created and user is not None
    assert user.email == "admin@nyanguholdings.com" and user.username == "admin"
    assert user.role_names == {"SUPER_ADMIN"}

    same, created_again = seed_admin(db, "admin@nyanguholdings.com", "Other!Admin2026")
    assert not created_again and same.id == user.id
    assert db.scalar(select(func.count()).select_from(User)) == 1
    assert isinstance(user.id, uuid.UUID)
