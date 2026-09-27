"""Customers, suppliers, product categories and products."""

from __future__ import annotations

from tests.conftest import API


def test_customer_crud(client, auth_headers) -> None:
    sales = auth_headers("SALES_OFFICER")
    r = client.post(
        f"{API}/customers",
        json={
            "name": "Kafue  Hardware Ltd",
            "tpin": "1002003004",
            "email": "Orders@KafueHardware.co.zm",
            "phone": "+260 211 123456",
            "credit_limit": "50000",
        },
        headers=sales,
    )
    assert r.status_code == 201, r.text
    customer = r.json()["data"]
    assert customer["code"] == "CUS-00001"
    assert customer["name"] == "Kafue Hardware Ltd"
    assert customer["credit_limit"] == "50000.00"
    assert customer["payment_terms_days"] == 30  # from settings
    assert customer["email"] == "orders@kafuehardware.co.zm"

    listing = client.get(f"{API}/customers", params={"search": "kafue"}, headers=sales)
    assert listing.json()["data"]["meta"]["total"] == 1
    upd = client.put(
        f"{API}/customers/{customer['id']}",
        json={"payment_terms_days": 14, "credit_limit": None},
        headers=sales,
    )
    assert upd.status_code == 200
    assert upd.json()["data"]["payment_terms_days"] == 14
    assert upd.json()["data"]["credit_limit"] is None
    # Sales officers cannot delete customers.
    assert client.delete(f"{API}/customers/{customer['id']}", headers=sales).status_code == 403
    admin = auth_headers("ADMIN", username="admin1")
    assert client.delete(f"{API}/customers/{customer['id']}", headers=admin).status_code == 200


def test_customer_validation_and_filters(client, auth_headers) -> None:
    sales = auth_headers("SALES_OFFICER")
    bad = client.post(
        f"{API}/customers",
        json={"name": "X", "tpin": "12", "credit_limit": "-1", "customer_type": "ALIEN"},
        headers=sales,
    )
    assert bad.status_code == 422
    assert {"name", "tpin", "credit_limit", "customer_type"} <= {
        e["field"] for e in bad.json()["errors"]
    }
    client.post(
        f"{API}/customers",
        json={"name": "Mary Phiri", "customer_type": "INDIVIDUAL"},
        headers=sales,
    )
    client.post(f"{API}/customers", json={"name": "Zambeef Plc"}, headers=sales)
    individuals = client.get(
        f"{API}/customers", params={"customer_type": "INDIVIDUAL"}, headers=sales
    )
    assert [c["name"] for c in individuals.json()["data"]["items"]] == ["Mary Phiri"]
    sorted_desc = client.get(
        f"{API}/customers", params={"sort_by": "name", "sort_order": "desc"}, headers=sales
    )
    assert sorted_desc.json()["data"]["items"][0]["name"] == "Zambeef Plc"
    assert (
        client.get(f"{API}/customers", params={"sort_by": "tpin"}, headers=sales).status_code == 400
    )


def test_supplier_crud_and_permissions(client, auth_headers) -> None:
    buyer = auth_headers("PROCUREMENT_OFFICER")
    r = client.post(
        f"{API}/suppliers",
        json={"name": "Lafarge Zambia", "bank_name": "Stanbic", "bank_account_number": "9130001"},
        headers=buyer,
    )
    assert r.status_code == 201
    supplier = r.json()["data"]
    assert supplier["code"] == "SUP-00001"
    # Sales officers have no supplier access at all.
    assert client.get(f"{API}/suppliers", headers=auth_headers("SALES_OFFICER")).status_code == 403
    # Accountants can read but not write.
    accountant = auth_headers("ACCOUNTANT")
    assert client.get(f"{API}/suppliers/{supplier['id']}", headers=accountant).status_code == 200
    assert (
        client.put(
            f"{API}/suppliers/{supplier['id']}", json={"city": "Ndola"}, headers=accountant
        ).status_code
        == 403
    )
    deactivated = client.put(
        f"{API}/suppliers/{supplier['id']}", json={"is_active": False}, headers=buyer
    )
    assert deactivated.json()["data"]["is_active"] is False
    assert (
        client.get(f"{API}/suppliers", params={"is_active": True}, headers=buyer).json()["data"][
            "meta"
        ]["total"]
        == 0
    )


def test_products_and_categories(client, auth_headers) -> None:
    store = auth_headers("STOREKEEPER")
    category = client.post(
        f"{API}/product-categories", json={"name": "Building materials"}, headers=store
    ).json()["data"]
    dup = client.post(
        f"{API}/product-categories", json={"name": "Building materials"}, headers=store
    )
    assert dup.status_code == 409

    r = client.post(
        f"{API}/products",
        json={
            "sku": "cem-50kg",
            "name": "Cement 50kg",
            "category_id": category["id"],
            "unit": "bag",
            "cost_price": "95.00",
            "selling_price": "120",
            "reorder_level": "100",
        },
        headers=store,
    )
    assert r.status_code == 201, r.text
    product = r.json()["data"]
    assert product["sku"] == "CEM-50KG"
    assert product["tax_rate"] == "16.00"  # default VAT
    assert product["category"]["name"] == "Building materials"
    assert product["selling_price"] == "120.00"

    service = client.post(
        f"{API}/products",
        json={
            "sku": "DELIVERY",
            "name": "Delivery fee",
            "product_type": "SERVICE",
            "selling_price": "250",
            "tax_rate": "0",
        },
        headers=store,
    ).json()["data"]
    assert service["tax_rate"] == "0.00"

    dup_sku = client.post(
        f"{API}/products", json={"sku": "CEM-50KG", "name": "Again"}, headers=store
    )
    assert dup_sku.status_code == 409
    goods = client.get(f"{API}/products", params={"product_type": "GOODS"}, headers=store)
    assert [p["sku"] for p in goods.json()["data"]["items"]] == ["CEM-50KG"]
    by_category = client.get(
        f"{API}/products", params={"category_id": category["id"]}, headers=store
    )
    assert by_category.json()["data"]["meta"]["total"] == 1

    # A category in use cannot be deleted.
    in_use = client.delete(f"{API}/product-categories/{category['id']}", headers=store)
    assert in_use.status_code == 422
    # Sales officers can read products but not change them.
    sales = auth_headers("SALES_OFFICER")
    assert client.get(f"{API}/products", headers=sales).status_code == 200
    assert (
        client.put(
            f"{API}/products/{product['id']}", json={"selling_price": "1"}, headers=sales
        ).status_code
        == 403
    )


def test_inactive_category_cannot_be_used(client, auth_headers) -> None:
    store = auth_headers("STOREKEEPER")
    category = client.post(
        f"{API}/product-categories", json={"name": "Old stuff"}, headers=store
    ).json()["data"]
    client.put(
        f"{API}/product-categories/{category['id']}", json={"is_active": False}, headers=store
    )
    r = client.post(
        f"{API}/products",
        json={"sku": "OLD-1", "name": "Old item", "category_id": category["id"]},
        headers=store,
    )
    assert r.status_code == 422
