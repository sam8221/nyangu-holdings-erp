"""Warehouses, stock levels, adjustments, transfers and low-stock alerts."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.partners import Product
from app.services.inventory_service import InventoryService
from tests.conftest import API, bearer, login


def setup_stock(client, admin) -> dict:
    wh1 = client.post(
        f"{API}/warehouses", json={"code": "LSK", "name": "Lusaka store"}, headers=admin
    ).json()["data"]
    wh2 = client.post(
        f"{API}/warehouses", json={"code": "NDL", "name": "Ndola store"}, headers=admin
    ).json()["data"]
    product = client.post(
        f"{API}/products",
        json={
            "sku": "CEM",
            "name": "Cement",
            "unit": "bag",
            "cost_price": "90",
            "selling_price": "120",
            "reorder_level": "10",
        },
        headers=admin,
    ).json()["data"]
    return {"wh1": wh1, "wh2": wh2, "product": product}


def test_warehouses_readable_by_everyone(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    setup_stock(client, admin)
    sales = auth_headers("SALES_OFFICER")
    assert client.get(f"{API}/warehouses", headers=sales).json()["data"]["meta"]["total"] == 2
    assert (
        client.post(
            f"{API}/warehouses", json={"code": "X", "name": "Nope"}, headers=sales
        ).status_code
        == 403
    )


def test_adjustment_by_change_and_by_count(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = setup_stock(client, admin)
    r = client.post(
        f"{API}/inventory/adjustments",
        json={
            "warehouse_id": s["wh1"]["id"],
            "reason": "Opening balance",
            "lines": [{"product_id": s["product"]["id"], "quantity_change": "50"}],
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    result = r.json()["data"]
    assert result["reference_number"].startswith("ADJ-")
    assert result["movements"][0]["balance_after"] == "50.000"

    counted = client.post(
        f"{API}/inventory/adjustments",
        json={
            "warehouse_id": s["wh1"]["id"],
            "reason": "Stock count",
            "lines": [{"product_id": s["product"]["id"], "counted_quantity": "47"}],
        },
        headers=admin,
    ).json()["data"]
    assert counted["movements"][0]["quantity"] == "-3.000"

    same = client.post(
        f"{API}/inventory/adjustments",
        json={
            "warehouse_id": s["wh1"]["id"],
            "reason": "Recount",
            "lines": [{"product_id": s["product"]["id"], "counted_quantity": "47"}],
        },
        headers=admin,
    )
    assert same.status_code == 422

    stock = client.get(f"{API}/inventory/products/{s['product']['id']}", headers=admin).json()
    assert stock["data"]["total_quantity"] == "47.000"
    assert stock["data"]["stock_value"] == "4230.00"


def test_stock_never_goes_negative(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = setup_stock(client, admin)
    r = client.post(
        f"{API}/inventory/adjustments",
        json={
            "warehouse_id": s["wh1"]["id"],
            "reason": "Breakage",
            "lines": [{"product_id": s["product"]["id"], "quantity_change": "-1"}],
        },
        headers=admin,
    )
    assert r.status_code == 422
    assert "Insufficient stock" in r.json()["message"]
    both = client.post(
        f"{API}/inventory/adjustments",
        json={
            "warehouse_id": s["wh1"]["id"],
            "reason": "Bad line",
            "lines": [
                {"product_id": s["product"]["id"], "quantity_change": "1", "counted_quantity": "2"}
            ],
        },
        headers=admin,
    )
    assert both.status_code == 422


def test_transfer_between_warehouses(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = setup_stock(client, admin)
    client.post(
        f"{API}/inventory/adjustments",
        json={
            "warehouse_id": s["wh1"]["id"],
            "reason": "Opening",
            "lines": [{"product_id": s["product"]["id"], "quantity_change": "30"}],
        },
        headers=admin,
    )
    store = auth_headers("STOREKEEPER")
    r = client.post(
        f"{API}/inventory/transfers",
        json={
            "from_warehouse_id": s["wh1"]["id"],
            "to_warehouse_id": s["wh2"]["id"],
            "lines": [{"product_id": s["product"]["id"], "quantity": "12.5"}],
        },
        headers=store,
    )
    assert r.status_code == 201, r.text
    moves = r.json()["data"]["movements"]
    assert [m["movement_type"] for m in moves] == ["TRANSFER_OUT", "TRANSFER_IN"]

    levels = client.get(
        f"{API}/inventory/stock-levels", params={"product_id": s["product"]["id"]}, headers=store
    ).json()["data"]["items"]
    by_code = {lvl["warehouse"]["code"]: lvl["quantity"] for lvl in levels}
    assert by_code == {"LSK": "17.500", "NDL": "12.500"}

    too_much = client.post(
        f"{API}/inventory/transfers",
        json={
            "from_warehouse_id": s["wh2"]["id"],
            "to_warehouse_id": s["wh1"]["id"],
            "lines": [{"product_id": s["product"]["id"], "quantity": "13"}],
        },
        headers=store,
    )
    assert too_much.status_code == 422
    same = client.post(
        f"{API}/inventory/transfers",
        json={
            "from_warehouse_id": s["wh1"]["id"],
            "to_warehouse_id": s["wh1"]["id"],
            "lines": [{"product_id": s["product"]["id"], "quantity": "1"}],
        },
        headers=store,
    )
    assert same.status_code == 422

    ledger = client.get(
        f"{API}/inventory/movements",
        params={"reference_number": moves[0]["reference_number"]},
        headers=store,
    )
    assert ledger.json()["data"]["meta"]["total"] == 2


def test_services_hold_no_stock(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = setup_stock(client, admin)
    service = client.post(
        f"{API}/products",
        json={"sku": "SVC", "name": "Consulting", "product_type": "SERVICE"},
        headers=admin,
    ).json()["data"]
    r = client.post(
        f"{API}/inventory/adjustments",
        json={
            "warehouse_id": s["wh1"]["id"],
            "reason": "Oops",
            "lines": [{"product_id": service["id"], "quantity_change": "1"}],
        },
        headers=admin,
    )
    assert r.status_code == 422


def test_low_stock_list_and_alert(client, make_user, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = setup_stock(client, admin)
    keeper = make_user("STOREKEEPER")
    keeper_h = bearer(login(client, keeper.email)["access_token"])
    client.post(
        f"{API}/inventory/adjustments",
        json={
            "warehouse_id": s["wh1"]["id"],
            "reason": "Opening",
            "lines": [{"product_id": s["product"]["id"], "quantity_change": "15"}],
        },
        headers=admin,
    )
    assert client.get(f"{API}/inventory/low-stock", headers=keeper_h).json()["data"]["items"] == []

    client.post(
        f"{API}/inventory/adjustments",
        json={
            "warehouse_id": s["wh1"]["id"],
            "reason": "Damaged",
            "lines": [{"product_id": s["product"]["id"], "quantity_change": "-6"}],
        },
        headers=admin,
    )
    low = client.get(f"{API}/inventory/low-stock", headers=keeper_h).json()["data"]["items"]
    assert (
        low[0]["sku"] == "CEM" and low[0]["on_hand"] == "9.000" and low[0]["shortfall"] == "1.000"
    )
    alerts = client.get(f"{API}/notifications", headers=keeper_h).json()["data"]["items"]
    assert [a["title"] for a in alerts] == ["Low stock: CEM"]


def test_weighted_average_cost_on_receipt(db: Session, client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = setup_stock(client, admin)
    product = db.get(Product, uuid.UUID(s["product"]["id"]))
    service = InventoryService(db)
    wh = uuid.UUID(s["wh1"]["id"])
    service.receive(
        product=product,
        warehouse_id=wh,
        quantity=Decimal("10"),
        unit_cost=Decimal("100"),
        actor=None,
    )
    assert product.cost_price == Decimal("100.00")  # nothing was on hand before
    service.receive(
        product=product,
        warehouse_id=wh,
        quantity=Decimal("30"),
        unit_cost=Decimal("80"),
        actor=None,
    )
    assert product.cost_price == Decimal("85.00")  # (10*100 + 30*80) / 40
    db.commit()


def test_warehouse_with_stock_cannot_be_deactivated(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = setup_stock(client, admin)
    client.post(
        f"{API}/inventory/adjustments",
        json={
            "warehouse_id": s["wh1"]["id"],
            "reason": "Opening",
            "lines": [{"product_id": s["product"]["id"], "quantity_change": "5"}],
        },
        headers=admin,
    )
    r = client.put(f"{API}/warehouses/{s['wh1']['id']}", json={"is_active": False}, headers=admin)
    assert r.status_code == 422
    assert (
        client.put(
            f"{API}/warehouses/{s['wh2']['id']}", json={"is_active": False}, headers=admin
        ).status_code
        == 200
    )
    # Products with stock history cannot switch to a service.
    change = client.put(
        f"{API}/products/{s['product']['id']}", json={"product_type": "SERVICE"}, headers=admin
    )
    assert change.status_code == 422
