"""Quotations, tax-inclusive pricing and the printed quotation/invoice layout."""

from __future__ import annotations

import io
from datetime import timedelta
from decimal import Decimal

from pypdf import PdfReader

from app.services.pricing import document_totals, line_amounts
from app.utils.time import local_today
from tests.conftest import API
from tests.factories import customer, post, product, stock, warehouse

# The lines of Nyangu's sample quotation (CLIENT-3.pdf): quantity and VAT-inclusive price.
SAMPLE = [
    (15, 450),
    (15, 650),
    (20, 700),
    (30, 750),
    (40, 1250),
    (20, 1380),
    (20, 3450),
    (10, 3700),
    (6, 4000),
]


def pdf_text(content: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(content)).pages)


def test_tax_inclusive_pricing_matches_the_sample_quotation() -> None:
    lines = [
        line_amounts(Decimal(q), Decimal(p), Decimal(0), Decimal(16), inclusive=True)
        for q, p in SAMPLE
    ]
    assert [str(ln.tax) for ln in lines][:3] == ["931.03", "1344.83", "1931.03"]
    assert lines[0].total == Decimal("6750.00") and lines[0].subtotal == Decimal("5818.97")
    totals = document_totals(lines, inclusive=True)
    assert totals.total == Decimal("260600.00")
    assert totals.tax_total == Decimal("35944.83")  # extracted from the total, like the sample
    assert totals.subtotal == Decimal("224655.17")


def _setup(client, admin) -> dict:
    wh = warehouse(client, admin)
    items = []
    for i, (qty, price) in enumerate(SAMPLE):
        p = product(
            client,
            admin,
            sku=f"CHINT-{i}",
            name=f"Contactor {i}",
            selling_price=str(price),
            unit="pcs",
        )
        stock(client, admin, wh["id"], p["id"], "100")
        items.append((p, qty))
    cust = customer(client, admin, name="Lusaka Water & Sanitation Company Limited")
    return {"warehouse": wh, "items": items, "customer": cust}


def _quote(client, headers, s, **extra) -> dict:
    return post(
        client,
        "/sales/quotations",
        {
            "customer_id": s["customer"]["id"],
            "customer_reference": "LWSC-PO-7781",
            "lines": [{"product_id": p["id"], "quantity": str(q)} for p, q in s["items"]],
            **extra,
        },
        headers,
    )


def test_quotation_defaults_and_totals(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = _setup(client, admin)
    quote = _quote(client, auth_headers("SALES_OFFICER"), s)
    assert quote["quote_number"] == f"QUO-{local_today().year}-00001"
    assert quote["status"] == "DRAFT" and quote["prices_include_tax"] is True
    assert quote["valid_until"] == (local_today() + timedelta(days=30)).isoformat()
    assert quote["total"] == "260600.00"
    assert quote["tax_total"] == "35944.83"
    assert quote["subtotal"] == "224655.17"
    first = quote["lines"][0]
    assert (
        first["unit_price"] == "450.00"
        and first["line_tax"] == "931.03"
        and first["line_total"] == "6750.00"
    )


def test_quotation_status_edit_and_delete_rules(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = _setup(client, admin)
    quote = _quote(client, admin, s)
    qid = quote["id"]

    sent = client.post(
        f"{API}/sales/quotations/{qid}/status", json={"status": "SENT"}, headers=admin
    )
    assert sent.status_code == 200 and sent.json()["data"]["status"] == "SENT"
    # Sent quotations can still be revised; switching to tax-exclusive recalculates.
    revised = client.put(
        f"{API}/sales/quotations/{qid}", json={"prices_include_tax": False}, headers=admin
    ).json()["data"]
    assert revised["subtotal"] == "260600.00" and revised["tax_total"] == "41696.00"
    assert client.delete(f"{API}/sales/quotations/{qid}", headers=admin).status_code == 422

    client.post(f"{API}/sales/quotations/{qid}/status", json={"status": "DECLINED"}, headers=admin)
    frozen = client.put(f"{API}/sales/quotations/{qid}", json={"notes": "x"}, headers=admin)
    assert frozen.status_code == 422
    no_convert = client.post(f"{API}/sales/quotations/{qid}/convert", headers=admin)
    assert no_convert.status_code == 422

    draft = _quote(client, admin, s)
    assert client.delete(f"{API}/sales/quotations/{draft['id']}", headers=admin).status_code == 200
    bad_dates = client.post(
        f"{API}/sales/quotations",
        json={
            "customer_id": s["customer"]["id"],
            "quote_date": "2026-09-16",
            "valid_until": "2026-09-01",
            "lines": [{"product_id": s["items"][0][0]["id"], "quantity": "1"}],
        },
        headers=admin,
    )
    assert bad_dates.status_code == 422
    listing = client.get(
        f"{API}/sales/quotations", params={"search": "lusaka water"}, headers=admin
    )
    assert listing.json()["data"]["meta"]["total"] == 1


def test_convert_quotation_to_invoice(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    s = _setup(client, admin)
    quote = _quote(client, admin, s)
    client.post(
        f"{API}/sales/quotations/{quote['id']}/status", json={"status": "ACCEPTED"}, headers=admin
    )

    r = client.post(
        f"{API}/sales/quotations/{quote['id']}/convert",
        json={"warehouse_id": s["warehouse"]["id"]},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    invoice = r.json()["data"]
    assert invoice["status"] == "DRAFT" and invoice["prices_include_tax"] is True
    assert invoice["total"] == "260600.00" and invoice["tax_total"] == "35944.83"
    assert invoice["customer_reference"] == "LWSC-PO-7781"
    assert quote["quote_number"] in invoice["notes"]

    converted = client.get(f"{API}/sales/quotations/{quote['id']}", headers=admin).json()["data"]
    assert converted["status"] == "CONVERTED" and converted["invoice_id"] == invoice["id"]
    again = client.post(f"{API}/sales/quotations/{quote['id']}/convert", headers=admin)
    assert again.status_code == 422

    issued = client.post(f"{API}/sales/invoices/{invoice['id']}/approve", headers=admin)
    assert issued.status_code == 200
    stock_after = client.get(f"{API}/inventory/products/{s['items'][0][0]['id']}", headers=admin)
    assert stock_after.json()["data"]["total_quantity"] == "85.000"  # 100 - 15


def test_invoices_follow_the_tax_inclusive_setting(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    wh = warehouse(client, admin)
    goods = product(client, admin, selling_price="116")
    stock(client, admin, wh["id"], goods["id"], "10")
    cust = customer(client, admin)
    body = {
        "customer_id": cust["id"],
        "warehouse_id": wh["id"],
        "lines": [{"product_id": goods["id"], "quantity": "1"}],
    }

    inclusive = post(client, "/sales/invoices", body, admin)
    assert inclusive["prices_include_tax"] is True
    assert (
        inclusive["total"] == "116.00"
        and inclusive["tax_total"] == "16.00"
        and inclusive["subtotal"] == "100.00"
    )

    client.put(f"{API}/settings", json={"prices_include_tax": False}, headers=admin)
    exclusive = post(client, "/sales/invoices", body, admin)
    assert exclusive["prices_include_tax"] is False and exclusive["total"] == "134.56"

    toggled = client.put(
        f"{API}/sales/invoices/{exclusive['id']}", json={"prices_include_tax": True}, headers=admin
    ).json()["data"]
    assert toggled["total"] == "116.00"


def test_quotation_and_invoice_pdfs(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    client.put(
        f"{API}/company",
        json={
            "legal_name": "Nyangu Holding Group Ltd",
            "tpin": "12003798438",
            "vat_number": "12003798438",
            "phone": "+260777204960",
            "email": "nyangugroup@gmail.com",
            "address": "P.O Box 1488, Plot No.1701 Off Makoli Road, Ndola",
        },
        headers=admin,
    )
    s = _setup(client, admin)
    quote = _quote(client, admin, s)
    r = client.get(f"{API}/sales/quotations/{quote['id']}/pdf", headers=admin)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    text = pdf_text(r.content)
    for expected in (
        "Quotation",
        "NYANGU HOLDING GROUP LTD",
        "12003798438",
        "LUSAKA WATER & SANITATION COMPANY LIMITED",
        quote["quote_number"],
        "LWSC-PO-7781",
        "Price (In)",
        "TaxInclusive",
        "Total (Excl)",
        "224,655.17",
        "35,944.83",
        "260,600.00",
        "Valid until",
        "Page 1 of 1",
    ):
        assert expected in text, expected

    invoice = client.post(
        f"{API}/sales/quotations/{quote['id']}/convert",
        json={"warehouse_id": s["warehouse"]["id"]},
        headers=admin,
    ).json()["data"]
    client.post(f"{API}/sales/invoices/{invoice['id']}/approve", headers=admin)
    inv_pdf = pdf_text(
        client.get(f"{API}/sales/invoices/{invoice['id']}/pdf", headers=admin).content
    )
    assert "Tax Invoice" in inv_pdf and "Balance Due" in inv_pdf and "260,600.00" in inv_pdf
