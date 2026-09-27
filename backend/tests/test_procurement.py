"""Purchase orders, approvals and goods receipts."""

from __future__ import annotations

from tests.conftest import API, bearer, login
from tests.factories import post, product, supplier, warehouse


def _setup(client, admin) -> dict:
    wh = warehouse(client, admin)
    goods = product(client, admin, cost_price="90")
    service = product(client, admin, sku="INSTALL", product_type="SERVICE", cost_price="0")
    sup = supplier(client, admin)
    return {"warehouse": wh, "goods": goods, "service": service, "supplier": sup}


def _order(client, headers, s: dict, quantity: str = "100", unit_cost: str = "80") -> dict:
    return post(
        client,
        "/procurement/purchase-orders",
        {
            "supplier_id": s["supplier"]["id"],
            "warehouse_id": s["warehouse"]["id"],
            "supplier_reference": "Q-2291",
            "lines": [
                {"product_id": s["goods"]["id"], "quantity": quantity, "unit_cost": unit_cost},
                {
                    "product_id": s["service"]["id"],
                    "quantity": "1",
                    "unit_cost": "500",
                    "tax_rate": "0",
                },
            ],
        },
        headers,
    )


def test_purchase_order_draft_and_approval(client, auth_headers, make_user) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = _setup(client, admin)
    buyer = make_user("PROCUREMENT_OFFICER")
    buyer_h = bearer(login(client, buyer.email)["access_token"])
    approver = make_user("MANAGER")
    approver_h = bearer(login(client, approver.email)["access_token"])

    po = _order(client, buyer_h, s)
    assert po["po_number"].startswith("PO-") and po["status"] == "DRAFT"
    assert po["subtotal"] == "8500.00" and po["tax_total"] == "1280.00" and po["total"] == "9780.00"
    notes = client.get(f"{API}/notifications", headers=approver_h).json()["data"]["items"]
    assert any(n["entity_id"] == po["id"] for n in notes)

    # The buyer cannot approve; the manager can.
    assert (
        client.post(
            f"{API}/procurement/purchase-orders/{po['id']}/approve", headers=buyer_h
        ).status_code
        == 403
    )
    approved = client.post(
        f"{API}/procurement/purchase-orders/{po['id']}/approve", headers=approver_h
    )
    assert approved.status_code == 200 and approved.json()["data"]["status"] == "APPROVED"
    buyer_notes = client.get(f"{API}/notifications", headers=buyer_h).json()["data"]["items"]
    assert any("approved" in n["title"] for n in buyer_notes)
    # Approved orders are locked.
    assert (
        client.put(
            f"{API}/procurement/purchase-orders/{po['id']}", json={"notes": "x"}, headers=buyer_h
        ).status_code
        == 422
    )


def test_partial_and_full_receipt_updates_stock_and_cost(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = _setup(client, admin)
    po = _order(client, admin, s, quantity="100", unit_cost="80")
    client.post(f"{API}/procurement/purchase-orders/{po['id']}/approve", headers=admin)
    goods_line, service_line = po["lines"]

    store = auth_headers("STOREKEEPER")  # storekeepers may receive goods
    grn = post(
        client,
        "/procurement/goods-receipts",
        {
            "purchase_order_id": po["id"],
            "delivery_note": "DN-55",
            "lines": [{"purchase_order_line_id": goods_line["id"], "quantity": "60"}],
        },
        store,
    )
    assert grn["grn_number"].startswith("GRN-") and grn["po_number"] == po["po_number"]
    order = client.get(f"{API}/procurement/purchase-orders/{po['id']}", headers=admin).json()[
        "data"
    ]
    assert order["status"] == "PARTIALLY_RECEIVED"
    assert order["lines"][0]["received_quantity"] == "60.000"
    assert order["lines"][0]["outstanding_quantity"] == "40.000"
    assert order["received_value"] == "4800.00"

    stock = client.get(f"{API}/inventory/products/{s['goods']['id']}", headers=admin).json()["data"]
    assert stock["total_quantity"] == "60.000"
    prod = client.get(f"{API}/products/{s['goods']['id']}", headers=admin).json()["data"]
    assert prod["cost_price"] == "80.00"  # nothing was on hand, so the receipt cost wins

    over = client.post(
        f"{API}/procurement/goods-receipts",
        json={
            "purchase_order_id": po["id"],
            "lines": [{"purchase_order_line_id": goods_line["id"], "quantity": "41"}],
        },
        headers=store,
    )
    assert over.status_code == 422 and "outstanding" in over.json()["message"]

    post(
        client,
        "/procurement/goods-receipts",
        {
            "purchase_order_id": po["id"],
            "lines": [
                {"purchase_order_line_id": goods_line["id"], "quantity": "40", "unit_cost": "85"},
                {"purchase_order_line_id": service_line["id"], "quantity": "1"},
            ],
        },
        store,
    )
    done = client.get(f"{API}/procurement/purchase-orders/{po['id']}", headers=admin).json()["data"]
    assert done["status"] == "RECEIVED" and len(done["receipts"]) == 2
    prod = client.get(f"{API}/products/{s['goods']['id']}", headers=admin).json()["data"]
    assert prod["cost_price"] == "82.00"  # (60*80 + 40*85) / 100

    closed = client.post(
        f"{API}/procurement/goods-receipts",
        json={
            "purchase_order_id": po["id"],
            "lines": [{"purchase_order_line_id": goods_line["id"], "quantity": "1"}],
        },
        headers=store,
    )
    assert closed.status_code == 422


def test_cannot_receive_against_draft_or_foreign_line(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = _setup(client, admin)
    draft = _order(client, admin, s)
    r = client.post(
        f"{API}/procurement/goods-receipts",
        json={
            "purchase_order_id": draft["id"],
            "lines": [{"purchase_order_line_id": draft["lines"][0]["id"], "quantity": "1"}],
        },
        headers=admin,
    )
    assert r.status_code == 422

    other = _order(client, admin, s)
    client.post(f"{API}/procurement/purchase-orders/{other['id']}/approve", headers=admin)
    foreign = client.post(
        f"{API}/procurement/goods-receipts",
        json={
            "purchase_order_id": other["id"],
            "lines": [{"purchase_order_line_id": draft["lines"][0]["id"], "quantity": "1"}],
        },
        headers=admin,
    )
    assert foreign.status_code == 422


def test_cancel_and_close_rules(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = _setup(client, admin)
    po = _order(client, admin, s)
    client.post(f"{API}/procurement/purchase-orders/{po['id']}/approve", headers=admin)
    post(
        client,
        "/procurement/goods-receipts",
        {
            "purchase_order_id": po["id"],
            "lines": [{"purchase_order_line_id": po["lines"][0]["id"], "quantity": "10"}],
        },
        admin,
    )
    cancel = client.post(
        f"{API}/procurement/purchase-orders/{po['id']}/cancel",
        json={"reason": "Supplier out of stock"},
        headers=admin,
    )
    assert cancel.status_code == 422
    closed = client.post(
        f"{API}/procurement/purchase-orders/{po['id']}/close",
        json={"reason": "Supplier cannot deliver the rest"},
        headers=admin,
    )
    assert closed.status_code == 200 and closed.json()["data"]["status"] == "CLOSED"

    fresh = _order(client, admin, s)
    cancelled = client.post(
        f"{API}/procurement/purchase-orders/{fresh['id']}/cancel",
        json={"reason": "Duplicate order"},
        headers=admin,
    )
    assert cancelled.json()["data"]["status"] == "CANCELLED"


def test_draft_update_delete_and_filters(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = _setup(client, admin)
    po = _order(client, admin, s)
    upd = client.put(
        f"{API}/procurement/purchase-orders/{po['id']}",
        json={"lines": [{"product_id": s["goods"]["id"], "quantity": "10", "unit_cost": "50"}]},
        headers=admin,
    )
    assert upd.status_code == 200 and upd.json()["data"]["total"] == "580.00"
    dup = client.put(
        f"{API}/procurement/purchase-orders/{po['id']}",
        json={
            "lines": [
                {"product_id": s["goods"]["id"], "quantity": "1"},
                {"product_id": s["goods"]["id"], "quantity": "2"},
            ]
        },
        headers=admin,
    )
    assert dup.status_code == 422
    listing = client.get(
        f"{API}/procurement/purchase-orders",
        params={"search": "lafarge", "status": "DRAFT"},
        headers=admin,
    )
    assert listing.json()["data"]["meta"]["total"] == 1
    assert (
        client.delete(f"{API}/procurement/purchase-orders/{po['id']}", headers=admin).status_code
        == 200
    )
    # Accountants can read purchase orders, not create them.
    accountant = auth_headers("ACCOUNTANT")
    assert client.get(f"{API}/procurement/purchase-orders", headers=accountant).status_code == 200
    assert (
        client.post(
            f"{API}/procurement/purchase-orders",
            json={
                "supplier_id": s["supplier"]["id"],
                "warehouse_id": s["warehouse"]["id"],
                "lines": [{"product_id": s["goods"]["id"], "quantity": "1"}],
            },
            headers=accountant,
        ).status_code
        == 403
    )
