"""Sales invoices, stock issue, credit limits, payments and PDFs."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from app.services.pricing import line_amounts
from app.utils.time import local_today
from tests.conftest import API
from tests.factories import issued_invoice, post, trading_setup


def _stock_total(client, admin, product_id: str) -> str:
    return client.get(f"{API}/inventory/products/{product_id}", headers=admin).json()["data"][
        "total_quantity"
    ]


def test_line_amounts_rounding() -> None:
    calc = line_amounts(Decimal("3"), Decimal("33.335"), Decimal("10"), Decimal("16"))
    assert calc.discount_amount == Decimal("10.00")  # 100.01 * 10% = 10.001
    assert calc.subtotal == Decimal("90.01")
    assert calc.tax == Decimal("14.40")
    assert calc.total == Decimal("104.41")


def test_draft_invoice_totals_and_defaults(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = trading_setup(client, admin)
    sales = auth_headers("SALES_OFFICER")
    draft = post(
        client,
        "/sales/invoices",
        {
            "customer_id": s["customer"]["id"],
            "warehouse_id": s["warehouse"]["id"],
            "customer_reference": "PO-778",
            "lines": [
                {"product_id": s["goods"]["id"], "quantity": "10", "discount_percent": "5"},
                {"product_id": s["service"]["id"], "quantity": "1"},
            ],
        },
        sales,
    )
    assert draft["status"] == "DRAFT" and draft["invoice_number"] is None
    goods_line, service_line = draft["lines"]
    assert goods_line["unit_price"] == "120.00" and goods_line["tax_rate"] == "16.00"
    assert goods_line["discount_amount"] == "60.00"
    assert goods_line["line_subtotal"] == "1140.00" and goods_line["line_tax"] == "182.40"
    assert service_line["line_total"] == "200.00"
    assert draft["subtotal"] == "1340.00"
    assert draft["tax_total"] == "182.40"
    assert draft["total"] == "1522.40"
    assert draft["balance_due"] == "1522.40"
    assert draft["due_date"] == (local_today() + timedelta(days=30)).isoformat()
    # Drafts do not touch stock.
    assert _stock_total(client, admin, s["goods"]["id"]) == "100.000"


def test_issue_invoice_deducts_stock_and_numbers(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = trading_setup(client, admin)
    invoice = issued_invoice(client, admin, s, quantity="10")
    assert invoice["status"] == "ISSUED"
    assert invoice["invoice_number"] == f"INV-{local_today().year}-00001"
    assert _stock_total(client, admin, s["goods"]["id"]) == "90.000"

    moves = client.get(
        f"{API}/inventory/movements",
        params={"reference_number": invoice["invoice_number"]},
        headers=admin,
    ).json()["data"]["items"]
    assert moves[0]["movement_type"] == "SALE" and moves[0]["quantity"] == "-10.000"

    # Issued invoices are locked.
    edit = client.put(f"{API}/sales/invoices/{invoice['id']}", json={"notes": "x"}, headers=admin)
    assert edit.status_code == 422
    assert client.delete(f"{API}/sales/invoices/{invoice['id']}", headers=admin).status_code == 422


def test_sales_officer_cannot_approve(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = trading_setup(client, admin)
    sales = auth_headers("SALES_OFFICER")
    draft = post(
        client,
        "/sales/invoices",
        {
            "customer_id": s["customer"]["id"],
            "warehouse_id": s["warehouse"]["id"],
            "lines": [{"product_id": s["goods"]["id"], "quantity": "1"}],
        },
        sales,
    )
    r = client.post(f"{API}/sales/invoices/{draft['id']}/approve", headers=sales)
    assert r.status_code == 403
    manager = auth_headers("MANAGER")
    assert (
        client.post(f"{API}/sales/invoices/{draft['id']}/approve", headers=manager).status_code
        == 200
    )


def test_issue_fails_without_stock_or_warehouse(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = trading_setup(client, admin, quantity="5")
    too_many = post(
        client,
        "/sales/invoices",
        {
            "customer_id": s["customer"]["id"],
            "warehouse_id": s["warehouse"]["id"],
            "lines": [{"product_id": s["goods"]["id"], "quantity": "6"}],
        },
        admin,
    )
    r = client.post(f"{API}/sales/invoices/{too_many['id']}/approve", headers=admin)
    assert r.status_code == 422 and "Insufficient stock" in r.json()["message"]
    # Nothing was consumed: numbering and stock are rolled back together.
    assert _stock_total(client, admin, s["goods"]["id"]) == "5.000"

    no_wh = post(
        client,
        "/sales/invoices",
        {
            "customer_id": s["customer"]["id"],
            "lines": [{"product_id": s["goods"]["id"], "quantity": "1"}],
        },
        admin,
    )
    r = client.post(f"{API}/sales/invoices/{no_wh['id']}/approve", headers=admin)
    assert r.status_code == 422 and "warehouse" in r.json()["message"]

    # A services-only invoice needs no warehouse.
    services = post(
        client,
        "/sales/invoices",
        {
            "customer_id": s["customer"]["id"],
            "lines": [{"product_id": s["service"]["id"], "quantity": "2"}],
        },
        admin,
    )
    ok = client.post(f"{API}/sales/invoices/{services['id']}/approve", headers=admin)
    assert ok.status_code == 200
    assert ok.json()["data"]["invoice_number"].endswith("00001")


def test_credit_limit_is_enforced(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = trading_setup(client, admin)
    client.put(
        f"{API}/customers/{s['customer']['id']}", json={"credit_limit": "2000"}, headers=admin
    )
    issued_invoice(client, admin, s, quantity="10")  # 1392.00
    second = post(
        client,
        "/sales/invoices",
        {
            "customer_id": s["customer"]["id"],
            "warehouse_id": s["warehouse"]["id"],
            "lines": [{"product_id": s["goods"]["id"], "quantity": "5"}],
        },
        admin,
    )
    r = client.post(f"{API}/sales/invoices/{second['id']}/approve", headers=admin)
    assert r.status_code == 422 and "Credit limit exceeded" in r.json()["message"]


def test_payments_update_status_and_can_be_voided(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = trading_setup(client, admin)
    invoice = issued_invoice(client, admin, s, quantity="10")  # 1392.00
    accountant = auth_headers("ACCOUNTANT")

    part = post(
        client,
        f"/sales/invoices/{invoice['id']}/payments",
        {"amount": "400", "method": "MOBILE_MONEY", "reference": "MTN-123"},
        accountant,
    )
    assert (
        part["receipt_number"].startswith("RCT-")
        and part["invoice_number"] == invoice["invoice_number"]
    )
    after = client.get(f"{API}/sales/invoices/{invoice['id']}", headers=admin).json()["data"]
    assert after["status"] == "PARTIALLY_PAID" and after["balance_due"] == "992.00"

    over = client.post(
        f"{API}/sales/invoices/{invoice['id']}/payments",
        json={"amount": "1000", "method": "CASH"},
        headers=accountant,
    )
    assert over.status_code == 422

    rest = post(
        client,
        f"/sales/invoices/{invoice['id']}/payments",
        {"amount": "992.00", "method": "BANK_TRANSFER"},
        accountant,
    )
    paid = client.get(f"{API}/sales/invoices/{invoice['id']}", headers=admin).json()["data"]
    assert paid["status"] == "PAID" and paid["balance_due"] == "0.00" and len(paid["payments"]) == 2

    # Sales officers can see receipts but cannot take money or void.
    sales = auth_headers("SALES_OFFICER")
    assert client.get(f"{API}/sales/payments", headers=sales).json()["data"]["meta"]["total"] == 2
    assert (
        client.post(
            f"{API}/sales/invoices/{invoice['id']}/payments",
            json={"amount": "1", "method": "CASH"},
            headers=sales,
        ).status_code
        == 403
    )

    voided = client.post(
        f"{API}/sales/payments/{rest['id']}/void",
        json={"reason": "Bounced transfer"},
        headers=accountant,
    )
    assert voided.status_code == 200 and voided.json()["data"]["status"] == "VOIDED"
    reopened = client.get(f"{API}/sales/invoices/{invoice['id']}", headers=admin).json()["data"]
    assert reopened["status"] == "PARTIALLY_PAID" and reopened["balance_due"] == "992.00"
    again = client.post(
        f"{API}/sales/payments/{rest['id']}/void", json={"reason": "Twice"}, headers=accountant
    )
    assert again.status_code == 422


def test_cancel_invoice_returns_stock(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = trading_setup(client, admin)
    invoice = issued_invoice(client, admin, s, quantity="10")
    paid = issued_invoice(client, admin, s, quantity="1")
    post(
        client,
        f"/sales/invoices/{paid['id']}/payments",
        {"amount": "10", "method": "CASH"},
        admin,
    )
    blocked = client.post(
        f"{API}/sales/invoices/{paid['id']}/cancel", json={"reason": "Mistake"}, headers=admin
    )
    assert blocked.status_code == 422 and "Void the payments" in blocked.json()["message"]

    r = client.post(
        f"{API}/sales/invoices/{invoice['id']}/cancel",
        json={"reason": "Customer changed order"},
        headers=admin,
    )
    assert r.status_code == 200 and r.json()["data"]["status"] == "CANCELLED"
    assert _stock_total(client, admin, s["goods"]["id"]) == "99.000"
    # Payments cannot be taken on a cancelled invoice.
    assert (
        client.post(
            f"{API}/sales/invoices/{invoice['id']}/payments",
            json={"amount": "1", "method": "CASH"},
            headers=admin,
        ).status_code
        == 422
    )


def test_invoice_filters_and_overdue(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = trading_setup(client, admin)
    old = post(
        client,
        "/sales/invoices",
        {
            "customer_id": s["customer"]["id"],
            "warehouse_id": s["warehouse"]["id"],
            "invoice_date": (local_today() - timedelta(days=60)).isoformat(),
            "due_date": (local_today() - timedelta(days=30)).isoformat(),
            "lines": [{"product_id": s["goods"]["id"], "quantity": "1"}],
        },
        admin,
    )
    client.post(f"{API}/sales/invoices/{old['id']}/approve", headers=admin)
    issued_invoice(client, admin, s, quantity="1")
    overdue = client.get(f"{API}/sales/invoices", params={"overdue": True}, headers=admin).json()[
        "data"
    ]
    assert overdue["meta"]["total"] == 1 and overdue["items"][0]["is_overdue"] is True
    by_name = client.get(
        f"{API}/sales/invoices", params={"search": "kafue", "status": "ISSUED"}, headers=admin
    )
    assert by_name.json()["data"]["meta"]["total"] == 2
    bad_dates = client.post(
        f"{API}/sales/invoices",
        json={
            "customer_id": s["customer"]["id"],
            "invoice_date": "2026-05-10",
            "due_date": "2026-05-01",
            "lines": [{"product_id": s["goods"]["id"], "quantity": "1"}],
        },
        headers=admin,
    )
    assert bad_dates.status_code == 422


def test_update_and_delete_draft(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = trading_setup(client, admin)
    draft = post(
        client,
        "/sales/invoices",
        {
            "customer_id": s["customer"]["id"],
            "lines": [{"product_id": s["goods"]["id"], "quantity": "1"}],
        },
        admin,
    )
    upd = client.put(
        f"{API}/sales/invoices/{draft['id']}",
        json={"lines": [{"product_id": s["goods"]["id"], "quantity": "2", "unit_price": "100"}]},
        headers=admin,
    )
    assert upd.status_code == 200
    assert upd.json()["data"]["total"] == "232.00" and len(upd.json()["data"]["lines"]) == 1
    assert client.delete(f"{API}/sales/invoices/{draft['id']}", headers=admin).status_code == 200
    assert client.get(f"{API}/sales/invoices/{draft['id']}", headers=admin).status_code == 404


def test_invoice_pdf(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = trading_setup(client, admin)
    invoice = issued_invoice(client, admin, s, quantity="2")
    r = client.get(f"{API}/sales/invoices/{invoice['id']}/pdf", headers=admin)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert invoice["invoice_number"] in r.headers["content-disposition"]
