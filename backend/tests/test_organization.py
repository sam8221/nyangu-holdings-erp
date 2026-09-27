"""Company profile, branches, departments and system settings."""

from __future__ import annotations

from tests.conftest import API


def test_company_profile_view_and_update(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    r = client.get(f"{API}/company", headers=admin)
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "Nyangu Holdings"
    assert r.json()["data"]["currency"] == "ZMW"

    updated = client.put(
        f"{API}/company",
        json={"legal_name": "Nyangu Holdings Limited", "tpin": "1001234567", "city": "Lusaka"},
        headers=admin,
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["tpin"] == "1001234567"
    bad = client.put(f"{API}/company", json={"tpin": "12AB"}, headers=admin)
    assert bad.status_code == 422
    assert client.put(f"{API}/company", json={"name": None}, headers=admin).status_code == 400
    assert (
        client.put(
            f"{API}/company", json={"city": "Ndola"}, headers=auth_headers("MANAGER")
        ).status_code
        == 403
    )


def test_branch_crud_and_single_head_office(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    hq = client.post(
        f"{API}/branches",
        json={"code": "lsk", "name": "Lusaka Head Office", "is_head_office": True},
        headers=admin,
    )
    assert hq.status_code == 201
    assert hq.json()["data"]["code"] == "LSK"
    ndola = client.post(
        f"{API}/branches",
        json={"code": "NDL", "name": "Ndola", "city": "Ndola", "is_head_office": True},
        headers=admin,
    ).json()["data"]
    # Only one head office at a time.
    first = client.get(f"{API}/branches/{hq.json()['data']['id']}", headers=admin).json()["data"]
    assert first["is_head_office"] is False and ndola["is_head_office"] is True

    dup = client.post(f"{API}/branches", json={"code": "LSK", "name": "Again"}, headers=admin)
    assert dup.status_code == 409
    bad = client.post(f"{API}/branches", json={"code": "has space", "name": "X Y"}, headers=admin)
    assert bad.status_code == 422

    # Any signed-in user can read branches; only company.update can change them.
    clerk = auth_headers("STOREKEEPER")
    listing = client.get(f"{API}/branches", params={"search": "ndola"}, headers=clerk)
    assert listing.status_code == 200 and listing.json()["data"]["meta"]["total"] == 1
    assert (
        client.post(
            f"{API}/branches", json={"code": "KIT", "name": "Kitwe"}, headers=clerk
        ).status_code
        == 403
    )

    renamed = client.put(
        f"{API}/branches/{ndola['id']}", json={"name": "Ndola Depot"}, headers=admin
    )
    assert renamed.json()["data"]["name"] == "Ndola Depot"
    assert client.delete(f"{API}/branches/{ndola['id']}", headers=admin).status_code == 200
    assert client.get(f"{API}/branches/{ndola['id']}", headers=admin).status_code == 404


def test_branch_in_use_cannot_be_deleted(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    branch = client.post(
        f"{API}/branches", json={"code": "KIT", "name": "Kitwe"}, headers=admin
    ).json()["data"]
    client.post(
        f"{API}/employees",
        json={
            "first_name": "Ruth",
            "last_name": "Mwansa",
            "hire_date": "2024-01-15",
            "branch_id": branch["id"],
        },
        headers=admin,
    )
    r = client.delete(f"{API}/branches/{branch['id']}", headers=admin)
    assert r.status_code == 422
    assert "Deactivate it instead" in r.json()["message"]


def test_department_crud(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    dept = client.post(f"{API}/departments", json={"code": "FIN", "name": "Finance"}, headers=admin)
    assert dept.status_code == 201
    dept_id = dept.json()["data"]["id"]
    dup_name = client.post(
        f"{API}/departments", json={"code": "FIN2", "name": "Finance"}, headers=admin
    )
    assert dup_name.status_code == 409
    upd = client.put(f"{API}/departments/{dept_id}", json={"is_active": False}, headers=admin)
    assert upd.json()["data"]["is_active"] is False
    active = client.get(f"{API}/departments", params={"is_active": True}, headers=admin)
    assert active.json()["data"]["meta"]["total"] == 0
    assert client.delete(f"{API}/departments/{dept_id}", headers=admin).status_code == 200


def test_settings_defaults_and_update(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    r = client.get(f"{API}/settings", headers=admin)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["default_vat_rate"] == "16.00"
    assert data["annual_leave_days"] == 24

    upd = client.put(
        f"{API}/settings", json={"annual_leave_days": 30, "default_vat_rate": "16.5"}, headers=admin
    )
    assert upd.status_code == 200
    assert upd.json()["data"]["annual_leave_days"] == 30
    assert upd.json()["data"]["default_vat_rate"] == "16.5"
    assert client.get(f"{API}/settings", headers=admin).json()["data"]["annual_leave_days"] == 30
    assert (
        client.put(f"{API}/settings", json={"default_vat_rate": 150}, headers=admin).status_code
        == 422
    )
    assert client.get(f"{API}/settings", headers=auth_headers("STOREKEEPER")).status_code == 403

    audit = client.get(f"{API}/audit-logs", params={"action": "settings."}, headers=admin)
    assert audit.json()["data"]["items"][0]["changes"]["annual_leave_days"] == {
        "from": 24,
        "to": 30,
    }
