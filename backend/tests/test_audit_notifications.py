"""Audit trail and in-app notifications."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.services.notifications import NotificationService
from app.utils.sequences import next_number
from app.utils.time import local_today
from tests.conftest import API, bearer, login, role_id


def test_user_changes_are_audited_with_diffs(client, auth_headers, make_user, db) -> None:
    admin = make_user("ADMIN", username="admin1")
    headers = bearer(login(client, admin.email)["access_token"])
    target = make_user(full_name="Old Name")
    client.put(
        f"{API}/users/{target.id}",
        json={"full_name": "New Name"},
        headers={**headers, "X-Request-ID": "req-123"},
    )
    client.put(
        f"{API}/users/{target.id}/roles",
        json={"role_ids": [role_id(db, "STOREKEEPER")]},
        headers=headers,
    )

    r = client.get(
        f"{API}/audit-logs", params={"entity_id": target.id, "action": "users."}, headers=headers
    )
    assert r.status_code == 200
    entries = {e["action"]: e for e in r.json()["data"]["items"]}
    update = entries["users.update"]
    assert update["changes"] == {"full_name": {"from": "Old Name", "to": "New Name"}}
    assert update["actor_id"] == admin.id and update["actor_label"] == admin.email
    assert update["request_id"] == "req-123"
    assert update["ip_address"] == "testclient"
    assert entries["users.roles"]["changes"]["roles"]["to"] == ["STOREKEEPER"]


def test_audit_log_records_logins_and_hides_secrets(client, make_user) -> None:
    admin = make_user("ADMIN", username="admin1")
    client.post(f"{API}/auth/login", json={"identifier": "ghost", "password": "Secret!Pass9"})
    headers = bearer(login(client, admin.email)["access_token"])
    r = client.get(f"{API}/audit-logs", params={"action": "auth."}, headers=headers)
    actions = [e["action"] for e in r.json()["data"]["items"]]
    assert "auth.login" in actions and "auth.login_failed" in actions
    assert "Secret!Pass9" not in r.text and "ghost" not in r.text


def test_audit_log_requires_permission_and_filters(client, auth_headers, make_user) -> None:
    assert client.get(f"{API}/audit-logs", headers=auth_headers("STOREKEEPER")).status_code == 403
    headers = auth_headers("MANAGER", username="boss")  # managers hold audit.view
    today = local_today().isoformat()
    r = client.get(
        f"{API}/audit-logs",
        params={"date_from": today, "date_to": today, "search": "user"},
        headers=headers,
    )
    assert r.status_code == 200
    one = r.json()["data"]["items"]
    if one:
        detail = client.get(f"{API}/audit-logs/{one[0]['id']}", headers=headers)
        assert detail.status_code == 200
    missing = client.get(f"{API}/audit-logs/{uuid.uuid4()}", headers=headers)
    assert missing.status_code == 404


def test_notifications_are_private_and_can_be_read(client, make_user, db: Session) -> None:
    alice = make_user("ACCOUNTANT")
    bob = make_user("ACCOUNTANT")
    service = NotificationService(db)
    service.notify([uuid.UUID(alice.id)], "Invoice approved", "INV-1 was approved")
    service.notify([uuid.UUID(alice.id)], "Stock low", "Cement is below reorder level")
    service.notify([uuid.UUID(bob.id)], "For Bob", "Only Bob sees this")
    db.commit()

    alice_h = bearer(login(client, alice.email)["access_token"])
    bob_h = bearer(login(client, bob.email)["access_token"])
    count = client.get(f"{API}/notifications/unread-count", headers=alice_h)
    assert count.json()["data"] == {"unread": 2}

    items = client.get(f"{API}/notifications", headers=alice_h).json()["data"]["items"]
    assert {n["title"] for n in items} == {"Invoice approved", "Stock low"}
    # Bob cannot read Alice's notification.
    assert (
        client.post(f"{API}/notifications/{items[0]['id']}/read", headers=bob_h).status_code == 404
    )

    read = client.post(f"{API}/notifications/{items[0]['id']}/read", headers=alice_h)
    assert read.status_code == 200 and read.json()["data"]["is_read"] is True
    unread = client.get(f"{API}/notifications", params={"unread_only": True}, headers=alice_h)
    assert unread.json()["data"]["meta"]["total"] == 1
    assert client.post(f"{API}/notifications/read-all", headers=alice_h).json()["data"] == {
        "updated": 1
    }


def test_notify_permission_targets_holders_only(db: Session, make_user) -> None:
    approver = make_user("HR_OFFICER")
    admin = make_user("SUPER_ADMIN")
    clerk = make_user("STOREKEEPER")
    inactive = make_user("HR_OFFICER", status="INACTIVE")
    holders = set(NotificationService(db).users_with_permission("leave.approve"))
    assert uuid.UUID(approver.id) in holders and uuid.UUID(admin.id) in holders
    assert uuid.UUID(clerk.id) not in holders and uuid.UUID(inactive.id) not in holders


def test_document_numbers_are_sequential(db: Session) -> None:
    year = local_today().year
    assert next_number(db, "INV") == f"INV-{year}-00001"
    assert next_number(db, "INV") == f"INV-{year}-00002"
    assert next_number(db, "PO") == f"PO-{year}-00001"
    assert next_number(db, "EMP", yearly=False) == "EMP-00001"
    db.rollback()  # rolled-back numbers are reused: no gaps
    assert next_number(db, "INV") == f"INV-{year}-00001"
    db.rollback()
