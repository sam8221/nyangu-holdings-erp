"""Fixed assets: register, depreciation, assignment and disposal."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.models.assets import Asset, months_between
from app.utils.time import local_today
from tests.conftest import API
from tests.factories import post


def _category(client, headers, **overrides) -> dict:
    body = {"name": "Motor vehicles", "useful_life_months": 60, **overrides}
    return post(client, "/asset-categories", body, headers)


def test_months_between() -> None:
    assert months_between(date(2024, 1, 15), date(2024, 2, 14)) == 0
    assert months_between(date(2024, 1, 15), date(2024, 2, 15)) == 1
    assert months_between(date(2024, 1, 31), date(2026, 1, 31)) == 24
    assert months_between(date(2024, 5, 1), date(2024, 4, 1)) == 0


def test_straight_line_depreciation_model() -> None:
    asset = Asset(
        purchase_date=date(2024, 1, 1),
        purchase_cost=Decimal("120000"),
        salvage_value=Decimal("12000"),
        depreciation_method="STRAIGHT_LINE",
        useful_life_months=60,
    )
    assert asset.monthly_depreciation == Decimal("1800")
    assert asset.accumulated_depreciation_at(date(2025, 1, 1)) == Decimal("21600.00")
    assert asset.book_value_at(date(2025, 1, 1)) == Decimal("98400.00")
    # Never depreciates below salvage value.
    assert asset.book_value_at(date(2035, 1, 1)) == Decimal("12000.00")


def test_asset_register_crud(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    category = _category(client, admin)
    purchased = local_today() - timedelta(days=400)
    r = client.post(
        f"{API}/assets",
        json={
            "name": "Toyota Hilux ABC 1234",
            "category_id": category["id"],
            "serial_number": "ahtfr22g",
            "purchase_date": purchased.isoformat(),
            "purchase_cost": "450000",
            "salvage_value": "50000",
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    asset = r.json()["data"]
    assert asset["asset_tag"] == "AST-00001"
    assert asset["depreciation_method"] == "STRAIGHT_LINE" and asset["useful_life_months"] == 60
    assert asset["serial_number"] == "AHTFR22G"
    assert Decimal(asset["accumulated_depreciation"]) > 0
    assert Decimal(asset["book_value"]) < Decimal("450000")

    dup = client.post(
        f"{API}/assets",
        json={
            "name": "Another",
            "category_id": category["id"],
            "serial_number": "AHTFR22G",
            "purchase_date": purchased.isoformat(),
            "purchase_cost": "1",
        },
        headers=admin,
    )
    assert dup.status_code == 409
    bad = client.post(
        f"{API}/assets",
        json={
            "name": "Bad",
            "category_id": category["id"],
            "purchase_date": purchased.isoformat(),
            "purchase_cost": "10",
            "salvage_value": "20",
        },
        headers=admin,
    )
    assert bad.status_code == 422

    schedule = client.get(f"{API}/assets/{asset['id']}/depreciation-schedule", headers=admin)
    years = schedule.json()["data"]["years"]
    assert years[0]["opening_value"] == "450000.00"
    assert years[-1]["closing_value"] == "50000.00"
    assert schedule.json()["data"]["monthly_depreciation"] == "6666.67"

    by_status = client.get(f"{API}/assets", params={"status": "IN_USE"}, headers=admin)
    assert by_status.json()["data"]["meta"]["total"] == 1


def test_assign_and_dispose(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    category = _category(client, admin, name="Computers", useful_life_months=36)
    employee = post(
        client,
        "/employees",
        {"first_name": "Chanda", "last_name": "Banda", "hire_date": "2022-02-01"},
        admin,
    )
    purchase = local_today() - timedelta(days=365 * 2)
    laptop = post(
        client,
        "/assets",
        {
            "name": "Dell Latitude",
            "category_id": category["id"],
            "purchase_date": purchase.isoformat(),
            "purchase_cost": "36000",
        },
        admin,
    )
    assigned = client.post(
        f"{API}/assets/{laptop['id']}/assign",
        json={"employee_id": employee["id"], "location": "Finance office"},
        headers=admin,
    )
    assert assigned.status_code == 200
    data = assigned.json()["data"]
    assert data["assigned_employee"]["full_name"] == "Chanda Banda"
    assert data["location"] == "Finance office"

    returned = client.post(
        f"{API}/assets/{laptop['id']}/assign", json={"employee_id": None}, headers=admin
    ).json()["data"]
    assert returned["status"] == "IN_STORE" and returned["assigned_employee"] is None

    disposed = client.post(
        f"{API}/assets/{laptop['id']}/dispose",
        json={
            "disposal_date": local_today().isoformat(),
            "disposal_value": "15000",
            "reason": "Sold to staff member",
        },
        headers=admin,
    )
    assert disposed.status_code == 200
    result = disposed.json()["data"]
    assert result["status"] == "DISPOSED"
    book = Decimal(result["book_value"])
    assert Decimal(result["disposal_gain_loss"]) == Decimal("15000.00") - book

    frozen = client.put(f"{API}/assets/{laptop['id']}", json={"name": "Renamed"}, headers=admin)
    assert frozen.status_code == 422
    again = client.post(
        f"{API}/assets/{laptop['id']}/dispose",
        json={"disposal_date": local_today().isoformat(), "disposal_value": "0", "reason": "Twice"},
        headers=admin,
    )
    assert again.status_code == 422


def test_asset_permissions(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    category = _category(client, admin)
    manager = auth_headers("MANAGER")  # assets.view only
    assert client.get(f"{API}/assets", headers=manager).status_code == 200
    r = client.post(
        f"{API}/assets",
        json={
            "name": "Desk",
            "category_id": category["id"],
            "purchase_date": "2024-01-01",
            "purchase_cost": "100",
        },
        headers=manager,
    )
    assert r.status_code == 403
    assert client.get(f"{API}/assets", headers=auth_headers("SALES_OFFICER")).status_code == 403
