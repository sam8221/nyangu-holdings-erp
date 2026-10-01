"""API-level helpers that set up common business data for tests."""

from __future__ import annotations

from typing import Any

from tests.conftest import API


def post(client, path: str, body: dict, headers: dict, expected: int = 201) -> dict[str, Any]:
    r = client.post(f"{API}{path}", json=body, headers=headers)
    assert r.status_code == expected, r.text
    return r.json()["data"]


def warehouse(client, headers, code: str = "LSK") -> dict:
    return post(client, "/warehouses", {"code": code, "name": f"{code} store"}, headers)


def product(client, headers, sku: str = "CEM", **overrides) -> dict:
    body = {
        "sku": sku,
        "name": f"Product {sku}",
        "unit": "bag",
        "cost_price": "90",
        "selling_price": "120",
        **overrides,
    }
    return post(client, "/products", body, headers)


def stock(client, headers, warehouse_id: str, product_id: str, quantity: str) -> None:
    post(
        client,
        "/inventory/adjustments",
        {
            "warehouse_id": warehouse_id,
            "reason": "Opening balance",
            "lines": [{"product_id": product_id, "quantity_change": quantity}],
        },
        headers,
    )


def customer(client, headers, name: str = "Kafue Hardware", **overrides) -> dict:
    return post(client, "/customers", {"name": name, **overrides}, headers)


def supplier(client, headers, name: str = "Lafarge Zambia", **overrides) -> dict:
    return post(client, "/suppliers", {"name": name, **overrides}, headers)


def trading_setup(client, admin, quantity: str = "100") -> dict:
    """A warehouse, a stocked product, a service and a customer."""
    wh = warehouse(client, admin)
    goods = product(client, admin)
    service = product(
        client, admin, sku="DELIVERY", product_type="SERVICE", selling_price="200", tax_rate="0"
    )
    stock(client, admin, wh["id"], goods["id"], quantity)
    cust = customer(client, admin)
    return {"warehouse": wh, "goods": goods, "service": service, "customer": cust}


def issued_invoice(client, admin, setup: dict, quantity: str = "10") -> dict:
    draft = post(
        client,
        "/sales/invoices",
        {
            "customer_id": setup["customer"]["id"],
            "warehouse_id": setup["warehouse"]["id"],
            "prices_include_tax": False,
            "lines": [{"product_id": setup["goods"]["id"], "quantity": quantity}],
        },
        admin,
    )
    return post(client, f"/sales/invoices/{draft['id']}/approve", {}, admin, expected=200)
