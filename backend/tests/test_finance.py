"""Expenses, supplier bills and payments, aging and customer statements."""

from __future__ import annotations

from datetime import timedelta

from app.utils.time import local_today
from tests.conftest import API, bearer, login
from tests.factories import post, product, supplier, trading_setup, warehouse


def _category(client, headers, name: str = "Fuel") -> dict:
    return post(client, "/finance/expense-categories", {"name": name}, headers)


def test_expense_approval_flow(client, make_user) -> None:
    clerk = make_user("ACCOUNTANT")
    clerk_h = bearer(login(client, clerk.email)["access_token"])
    boss = make_user("MANAGER")
    boss_h = bearer(login(client, boss.email)["access_token"])
    category = _category(client, clerk_h)

    expense = post(
        client,
        "/finance/expenses",
        {
            "category_id": category["id"],
            "payee": "Puma Energy",
            "description": "Diesel for delivery truck",
            "amount": "1500",
            "tax_amount": "240",
            "method": "CASH",
        },
        clerk_h,
    )
    assert expense["expense_number"].startswith("EXP-") and expense["total"] == "1740.00"
    assert expense["status"] == "PENDING"

    # Submitters cannot approve their own expenses.
    own = client.post(f"{API}/finance/expenses/{expense['id']}/approve", headers=clerk_h)
    assert own.status_code == 422
    notes = client.get(f"{API}/notifications", headers=boss_h).json()["data"]["items"]
    assert any(n["entity_id"] == expense["id"] for n in notes)

    approved = client.post(
        f"{API}/finance/expenses/{expense['id']}/approve",
        json={"comment": "OK"},
        headers=boss_h,
    )
    assert approved.status_code == 200 and approved.json()["data"]["status"] == "APPROVED"
    assert (
        client.put(
            f"{API}/finance/expenses/{expense['id']}", json={"amount": "1"}, headers=clerk_h
        ).status_code
        == 422
    )
    clerk_notes = client.get(f"{API}/notifications", headers=clerk_h).json()["data"]["items"]
    assert any("approved" in n["title"] for n in clerk_notes)


def test_expense_rules(client, auth_headers) -> None:
    accountant = auth_headers("ACCOUNTANT")
    category = _category(client, accountant)
    future = client.post(
        f"{API}/finance/expenses",
        json={
            "category_id": category["id"],
            "payee": "X Ltd",
            "description": "Future spend",
            "amount": "10",
            "expense_date": (local_today() + timedelta(days=3)).isoformat(),
        },
        headers=accountant,
    )
    assert future.status_code == 422
    zero = client.post(
        f"{API}/finance/expenses",
        json={
            "category_id": category["id"],
            "payee": "X Ltd",
            "description": "Nothing",
            "amount": "0",
        },
        headers=accountant,
    )
    assert zero.status_code == 422
    expense = post(
        client,
        "/finance/expenses",
        {
            "category_id": category["id"],
            "payee": "ZESCO",
            "description": "Electricity",
            "amount": "900",
        },
        accountant,
    )
    upd = client.put(
        f"{API}/finance/expenses/{expense['id']}", json={"amount": "950"}, headers=accountant
    )
    assert upd.json()["data"]["amount"] == "950.00"
    rejected = client.post(
        f"{API}/finance/expenses/{expense['id']}/reject",
        json={"comment": "Attach the ZESCO receipt"},
        headers=auth_headers("MANAGER"),
    )
    assert rejected.json()["data"]["status"] == "REJECTED"
    listing = client.get(
        f"{API}/finance/expenses",
        params={"status": "REJECTED", "search": "zesco"},
        headers=accountant,
    )
    assert listing.json()["data"]["meta"]["total"] == 1
    # Storekeepers have no finance access.
    assert (
        client.get(f"{API}/finance/expenses", headers=auth_headers("STOREKEEPER")).status_code
        == 403
    )


def _approved_order(client, admin) -> dict:
    wh = warehouse(client, admin)
    goods = product(client, admin)
    sup = supplier(client, admin)
    po = post(
        client,
        "/procurement/purchase-orders",
        {
            "supplier_id": sup["id"],
            "warehouse_id": wh["id"],
            "lines": [{"product_id": goods["id"], "quantity": "10", "unit_cost": "100"}],
        },
        admin,
    )  # total 1160.00
    client.post(f"{API}/procurement/purchase-orders/{po['id']}/approve", headers=admin)
    return {"po": po, "supplier": sup}


def test_supplier_bill_payment_flow(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = _approved_order(client, admin)
    accountant = auth_headers("ACCOUNTANT")
    bill = post(
        client,
        "/finance/bills",
        {
            "supplier_id": s["supplier"]["id"],
            "purchase_order_id": s["po"]["id"],
            "supplier_invoice_number": "LZ-4471",
            "subtotal": "1000",
            "tax_total": "160",
        },
        accountant,
    )
    assert bill["bill_number"].startswith("BILL-") and bill["status"] == "PENDING"
    assert bill["total"] == "1160.00"
    assert bill["due_date"] == (local_today() + timedelta(days=30)).isoformat()

    duplicate = client.post(
        f"{API}/finance/bills",
        json={
            "supplier_id": s["supplier"]["id"],
            "supplier_invoice_number": "LZ-4471",
            "subtotal": "5",
        },
        headers=accountant,
    )
    assert duplicate.status_code == 409
    over_po = client.post(
        f"{API}/finance/bills",
        json={
            "supplier_id": s["supplier"]["id"],
            "purchase_order_id": s["po"]["id"],
            "supplier_invoice_number": "LZ-4472",
            "subtotal": "1",
        },
        headers=accountant,
    )
    assert over_po.status_code == 422 and "exceed" in over_po.json()["message"]

    # A pending bill cannot be paid.
    assert (
        client.post(
            f"{API}/finance/bills/{bill['id']}/payments",
            json={"amount": "100", "method": "BANK_TRANSFER"},
            headers=accountant,
        ).status_code
        == 422
    )
    client.post(f"{API}/finance/bills/{bill['id']}/approve", headers=accountant)

    pay = post(
        client,
        f"/finance/bills/{bill['id']}/payments",
        {"amount": "500", "method": "BANK_TRANSFER", "reference": "EFT-0091"},
        accountant,
    )
    assert pay["payment_number"].startswith("PAY-") and pay["bill_number"] == bill["bill_number"]
    after = client.get(f"{API}/finance/bills/{bill['id']}", headers=accountant).json()["data"]
    assert after["status"] == "PARTIALLY_PAID" and after["balance_due"] == "660.00"
    too_much = client.post(
        f"{API}/finance/bills/{bill['id']}/payments",
        json={"amount": "661", "method": "CASH"},
        headers=accountant,
    )
    assert too_much.status_code == 422

    cancel = client.post(
        f"{API}/finance/bills/{bill['id']}/cancel", json={"reason": "Wrong"}, headers=accountant
    )
    assert cancel.status_code == 422
    voided = client.post(
        f"{API}/finance/supplier-payments/{pay['id']}/void",
        json={"reason": "Sent to the wrong account"},
        headers=accountant,
    )
    assert voided.json()["data"]["status"] == "VOIDED"
    reopened = client.get(f"{API}/finance/bills/{bill['id']}", headers=accountant).json()["data"]
    assert reopened["status"] == "APPROVED" and reopened["amount_paid"] == "0.00"


def test_bill_po_must_match_supplier(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = _approved_order(client, admin)
    other = supplier(client, admin, name="Other Supplier")
    r = client.post(
        f"{API}/finance/bills",
        json={
            "supplier_id": other["id"],
            "purchase_order_id": s["po"]["id"],
            "supplier_invoice_number": "X-1",
            "subtotal": "10",
        },
        headers=admin,
    )
    assert r.status_code == 422 and "different supplier" in r.json()["message"]


def test_receivables_aging_and_statement(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = trading_setup(client, admin)
    today = local_today()

    def invoice(days_ago: int, due_days_ago: int, qty: str) -> dict:
        draft = post(
            client,
            "/sales/invoices",
            {
                "customer_id": s["customer"]["id"],
                "warehouse_id": s["warehouse"]["id"],
                "invoice_date": (today - timedelta(days=days_ago)).isoformat(),
                "due_date": (today - timedelta(days=due_days_ago)).isoformat(),
                "lines": [
                    {
                        "product_id": s["goods"]["id"],
                        "quantity": qty,
                        "unit_price": "100",
                        "tax_rate": "0",
                    }
                ],
            },
            admin,
        )
        return post(client, f"/sales/invoices/{draft['id']}/approve", {}, admin, expected=200)

    old = invoice(120, 100, "5")  # 500, 100 days overdue
    mid = invoice(50, 40, "3")  # 300, 40 days overdue
    invoice(5, -25, "2")  # 200, not yet due
    post(
        client,
        f"/sales/invoices/{mid['id']}/payments",
        {
            "amount": "100",
            "method": "CASH",
            "payment_date": (today - timedelta(days=10)).isoformat(),
        },
        admin,
    )

    aging = client.get(f"{API}/finance/receivables", headers=admin).json()["data"]
    row = aging["rows"][0]
    assert row["party"]["name"] == "Kafue Hardware" and row["documents"] == 3
    assert row["current"] == "200.00"
    assert row["days_31_60"] == "200.00"
    assert row["days_over_90"] == "500.00"
    assert row["total"] == "900.00" and aging["totals"]["total"] == "900.00"

    statement = client.get(
        f"{API}/finance/customers/{s['customer']['id']}/statement",
        params={
            "date_from": (today - timedelta(days=60)).isoformat(),
            "date_to": today.isoformat(),
        },
        headers=admin,
    ).json()["data"]
    assert statement["opening_balance"] == "500.00"  # the old invoice predates the period
    assert [ln["type"] for ln in statement["lines"]] == ["INVOICE", "PAYMENT", "INVOICE"]
    assert statement["closing_balance"] == "900.00"
    assert statement["lines"][-1]["balance"] == "900.00"
    assert old["invoice_number"] not in str(statement["lines"])


def test_payables_aging(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    sup = supplier(client, admin)
    today = local_today()
    bill = post(
        client,
        "/finance/bills",
        {
            "supplier_id": sup["id"],
            "supplier_invoice_number": "S-1",
            "subtotal": "700",
            "bill_date": (today - timedelta(days=45)).isoformat(),
            "due_date": (today - timedelta(days=15)).isoformat(),
        },
        admin,
    )
    pending = client.get(f"{API}/finance/payables", headers=admin).json()["data"]
    assert pending["rows"] == []  # pending bills are not payables yet
    client.post(f"{API}/finance/bills/{bill['id']}/approve", headers=admin)
    aging = client.get(f"{API}/finance/payables", headers=admin).json()["data"]
    assert aging["rows"][0]["days_1_30"] == "700.00"
    overdue = client.get(f"{API}/finance/bills", params={"overdue": True}, headers=admin)
    assert overdue.json()["data"]["meta"]["total"] == 1
