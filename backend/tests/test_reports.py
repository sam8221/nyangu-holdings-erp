"""Dashboard, reports and exports, housekeeping, and production configuration guards."""

from __future__ import annotations

import io
from datetime import timedelta

import pytest
from openpyxl import load_workbook
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.system import Notification, PasswordResetToken
from app.tasks.housekeeping import run_housekeeping
from app.utils.time import local_today, utcnow
from tests.conftest import API
from tests.factories import issued_invoice, post, trading_setup


def _sales_with_expense(client, admin) -> dict:
    s = trading_setup(client, admin)
    inv = issued_invoice(client, admin, s, quantity="10")  # net 1200, VAT 192, cost 900
    post(
        client,
        f"/sales/invoices/{inv['id']}/payments",
        {"amount": "500", "method": "CASH"},
        admin,
    )
    category = post(client, "/finance/expense-categories", {"name": "Rent"}, admin)
    expense = post(
        client,
        "/finance/expenses",
        {
            "category_id": category["id"],
            "payee": "Landlord",
            "description": "Shop rent",
            "amount": "200",
            "tax_amount": "32",
        },
        admin,
    )
    return {"setup": s, "invoice": inv, "expense": expense}


def test_dashboard_sections_follow_permissions(client, auth_headers, make_user) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    _sales_with_expense(client, admin)

    full = client.get(f"{API}/dashboard/summary", headers=admin).json()["data"]
    assert full["currency"] == "ZMW"
    assert full["sales"]["invoiced_this_month"] == "1392.00"
    assert full["sales"]["collected_this_month"] == "500.00"
    assert full["sales"]["monthly_net_sales"][-1]["net_sales"] == "1200.00"
    assert len(full["sales"]["monthly_net_sales"]) == 6
    assert full["finance"]["receivables_outstanding"] == "892.00"
    assert full["inventory"]["stock_value"] == "8100.00"  # 90 bags at 90
    assert full["pending_approvals"]["expenses"] == 1  # the rent expense awaits approval

    store = auth_headers("STOREKEEPER")
    limited = client.get(f"{API}/dashboard/summary", headers=store).json()["data"]
    assert limited["inventory"] is not None
    assert limited["sales"] is None and limited["finance"] is None
    assert limited["pending_approvals"] == {}


def test_report_catalogue_and_permissions(client, auth_headers) -> None:
    manager = auth_headers("MANAGER")
    reports = client.get(f"{API}/reports", headers=manager).json()["data"]
    keys = {r["key"] for r in reports}
    assert {"sales-summary", "profit-and-loss", "vat-summary", "inventory-valuation"} <= keys
    assert client.get(f"{API}/reports", headers=auth_headers("STOREKEEPER")).status_code == 403
    assert client.get(f"{API}/reports/no-such-report", headers=manager).status_code == 404
    bad_group = client.get(
        f"{API}/reports/sales-summary", params={"group_by": "planet"}, headers=manager
    )
    assert bad_group.status_code == 400


def test_financial_reports(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    data = _sales_with_expense(client, admin)
    client.post(
        f"{API}/finance/expenses/{data['expense']['id']}/approve",
        headers=auth_headers("MANAGER"),
    )
    today = local_today().isoformat()
    period = {"date_from": (local_today() - timedelta(days=1)).isoformat(), "date_to": today}

    summary = client.get(
        f"{API}/reports/sales-summary", params={**period, "group_by": "customer"}, headers=admin
    ).json()["data"]
    assert summary["rows"][0]["group"] == "Kafue Hardware"
    assert summary["totals"]["gross_sales"] == "1392.00"

    by_product = client.get(f"{API}/reports/sales-by-product", params=period, headers=admin).json()[
        "data"
    ]
    row = by_product["rows"][0]
    assert row["revenue"] == "1200.00" and row["cost_of_sales"] == "900.00"
    assert row["gross_profit"] == "300.00" and row["margin_percent"] == "25.00"

    pnl = client.get(f"{API}/reports/profit-and-loss", params=period, headers=admin).json()["data"]
    lines = {r["line"]: r["amount"] for r in pnl["rows"]}
    assert lines["Revenue (net of VAT)"] == "1200.00"
    assert lines["Gross profit"] == "300.00"
    assert lines["Expense: Rent"] == "-200.00"
    assert lines["Net profit"] == "100.00"

    vat = client.get(f"{API}/reports/vat-summary", params=period, headers=admin).json()["data"]
    assert vat["totals"]["amount"] == "160.00"  # 192 output - 32 input

    valuation = client.get(f"{API}/reports/inventory-valuation", headers=admin).json()["data"]
    assert valuation["totals"]["value"] == "8100.00"
    aging = client.get(f"{API}/reports/receivables-aging", headers=admin).json()["data"]
    assert aging["totals"]["total"] == "892.00"
    moves = client.get(f"{API}/reports/stock-movements", params=period, headers=admin).json()
    assert (
        moves["data"]["rows"][0]["in"] == "100.000" and moves["data"]["rows"][0]["out"] == "10.000"
    )


def test_report_exports(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    _sales_with_expense(client, admin)
    csv_resp = client.get(f"{API}/reports/sales-summary", params={"format": "csv"}, headers=admin)
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")
    text = csv_resp.content.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("Month,Invoices,Net sales")
    assert "1392.00" in text

    xlsx = client.get(
        f"{API}/reports/inventory-valuation", params={"format": "xlsx"}, headers=admin
    )
    assert xlsx.status_code == 200
    sheet = load_workbook(io.BytesIO(xlsx.content)).active
    assert sheet["A1"].value == "Inventory valuation (weighted average cost)"

    # reports.view alone is not enough to export.
    root = auth_headers("SUPER_ADMIN", username="root")
    client.post(
        f"{API}/roles",
        json={
            "name": "REPORT_READER",
            "display_name": "Report reader",
            "permissions": ["reports.view"],
        },
        headers=root,
    )
    reader = auth_headers("REPORT_READER")
    assert client.get(f"{API}/reports/headcount", headers=reader).status_code == 200
    assert (
        client.get(f"{API}/reports/headcount", params={"format": "csv"}, headers=reader).status_code
        == 403
    )


def test_headcount_and_asset_reports(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    dept = post(client, "/departments", {"code": "OPS", "name": "Operations"}, admin)
    for name in ("Ann", "Ben"):
        post(
            client,
            "/employees",
            {
                "first_name": name,
                "last_name": "Zulu",
                "hire_date": "2023-01-01",
                "department_id": dept["id"],
            },
            admin,
        )
    report = client.get(f"{API}/reports/headcount", headers=admin).json()["data"]
    assert report["rows"][0]["group"] == "Operations" and report["rows"][0]["ACTIVE"] == 2
    assert report["totals"]["total"] == 2
    assets = client.get(f"{API}/reports/asset-register", headers=admin).json()["data"]
    assert assets["rows"] == []


def test_housekeeping_purges_stale_rows(db: Session, make_user) -> None:
    import uuid

    user = make_user()
    uid = uuid.UUID(user.id)
    old = utcnow() - timedelta(days=400)
    db.add_all(
        [
            PasswordResetToken(user_id=uid, token_hash="a" * 64, expires_at=old),
            PasswordResetToken(
                user_id=uid, token_hash="b" * 64, expires_at=utcnow() + timedelta(minutes=5)
            ),
            Notification(user_id=uid, title="old", message="x", is_read=True, created_at=old),
            Notification(user_id=uid, title="unread", message="x", is_read=False, created_at=old),
        ]
    )
    db.commit()
    result = run_housekeeping(db)
    assert result.password_reset_tokens == 1
    assert result.notifications == 1


def _settings(**overrides) -> Settings:
    base = {
        "DATABASE_URL": "postgresql+psycopg://u:p@localhost/db",
        "SECRET_KEY": "x" * 48,
        "_env_file": None,
    }
    return Settings(**{**base, **overrides})  # type: ignore[arg-type]


def test_production_configuration_guards() -> None:
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        _settings(ENVIRONMENT="production", CORS_ORIGINS="*")
    with pytest.raises(ValidationError, match="memory"):
        _settings(ENVIRONMENT="production", EMAIL_BACKEND="memory")
    with pytest.raises(ValidationError, match="SMTP_HOST"):
        _settings(EMAIL_BACKEND="smtp")
    assert _settings(
        ENVIRONMENT="production", CORS_ORIGINS="https://erp.nyangu.co.zm", EMAIL_BACKEND="console"
    )
