"""Customers, suppliers, product categories and products.

No ``from __future__ import annotations`` here: the filter dependencies must expose real types.
"""

import uuid
from typing import Annotated, Any

from fastapi import Query

from app.auth.permissions import Perm
from app.routers.crud import crud_router
from app.schemas.partners import (
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    CustomerCreate,
    CustomerOut,
    CustomerType,
    CustomerUpdate,
    ProductCreate,
    ProductOut,
    ProductType,
    ProductUpdate,
    SupplierCreate,
    SupplierOut,
    SupplierUpdate,
)
from app.services.partners_service import (
    CategoryService,
    CustomerService,
    ProductService,
    SupplierService,
)


def customer_filters(
    is_active: bool | None = None,
    customer_type: CustomerType | None = None,
) -> dict[str, Any]:
    return {"is_active": is_active, "customer_type": customer_type}


def active_filter(is_active: bool | None = None) -> dict[str, Any]:
    return {"is_active": is_active}


def product_filters(
    is_active: bool | None = None,
    product_type: ProductType | None = None,
    category_id: Annotated[uuid.UUID | None, Query()] = None,
) -> dict[str, Any]:
    return {"is_active": is_active, "product_type": product_type, "category_id": category_id}


customers_router = crud_router(
    prefix="/customers",
    tag="Customers",
    service=CustomerService,
    out=CustomerOut,
    create=CustomerCreate,
    update=CustomerUpdate,
    view_perm=Perm.CUSTOMERS_VIEW,
    create_perm=Perm.CUSTOMERS_CREATE,
    update_perm=Perm.CUSTOMERS_UPDATE,
    delete_perm=Perm.CUSTOMERS_DELETE,
    filters=customer_filters,
)

suppliers_router = crud_router(
    prefix="/suppliers",
    tag="Suppliers",
    service=SupplierService,
    out=SupplierOut,
    create=SupplierCreate,
    update=SupplierUpdate,
    view_perm=Perm.SUPPLIERS_VIEW,
    create_perm=Perm.SUPPLIERS_CREATE,
    update_perm=Perm.SUPPLIERS_UPDATE,
    delete_perm=Perm.SUPPLIERS_DELETE,
    filters=active_filter,
)

categories_router = crud_router(
    prefix="/product-categories",
    tag="Products",
    service=CategoryService,
    out=CategoryOut,
    create=CategoryCreate,
    update=CategoryUpdate,
    view_perm=Perm.PRODUCTS_VIEW,
    create_perm=Perm.PRODUCTS_CREATE,
    update_perm=Perm.PRODUCTS_UPDATE,
    delete_perm=Perm.PRODUCTS_DELETE,
    filters=active_filter,
)

products_router = crud_router(
    prefix="/products",
    tag="Products",
    service=ProductService,
    out=ProductOut,
    create=ProductCreate,
    update=ProductUpdate,
    view_perm=Perm.PRODUCTS_VIEW,
    create_perm=Perm.PRODUCTS_CREATE,
    update_perm=Perm.PRODUCTS_UPDATE,
    delete_perm=Perm.PRODUCTS_DELETE,
    filters=product_filters,
)
