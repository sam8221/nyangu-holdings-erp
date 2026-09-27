"""Router factory for standard master-data endpoints (list, create, get, update, delete).

This module deliberately does not use ``from __future__ import annotations``: the endpoint
signatures refer to classes passed in at runtime, and FastAPI must see the real objects.
"""

import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.auth.dependencies import (
    AuthContext,
    DbSession,
    get_auth_context,
    require_permissions,
)
from app.auth.permissions import Perm
from app.schemas.common import ApiResponse, Page, PageParams, error_responses, ok, page_params
from app.services.master_data import MasterDataService


def _no_filters() -> dict[str, Any]:
    return {}


def crud_router(
    *,
    prefix: str,
    tag: str,
    service: type[MasterDataService],
    out: type[BaseModel],
    create: type[BaseModel],
    update: type[BaseModel],
    view_perm: Perm | None,
    create_perm: Perm,
    update_perm: Perm,
    delete_perm: Perm,
    filters: Callable[..., dict[str, Any]] = _no_filters,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[tag])
    label = service.label
    lower = label.lower()
    sorts = ", ".join(sorted(service.sort_fields))

    # view_perm=None: any signed-in user may read (reference data needed by many forms).
    Viewer = Annotated[
        AuthContext,
        Depends(require_permissions(view_perm) if view_perm else get_auth_context),
    ]
    Creator = Annotated[AuthContext, Depends(require_permissions(create_perm))]
    Updater = Annotated[AuthContext, Depends(require_permissions(update_perm))]
    Deleter = Annotated[AuthContext, Depends(require_permissions(delete_perm))]
    Params = Annotated[PageParams, Depends(page_params)]
    Filters = Annotated[dict[str, Any], Depends(filters)]

    @router.get(
        "",
        summary=f"List {lower}s",
        description=f"Sort by: {sorts}.",
        response_model=ApiResponse[Page[out]],  # type: ignore[valid-type]
        responses=error_responses(400, 401, 403, 422),
    )
    def list_items(ctx: Viewer, db: DbSession, params: Params, filter_values: Filters) -> dict:
        return ok(service(db).list(params, **filter_values), f"{label}s retrieved")

    @router.post(
        "",
        summary=f"Create a {lower}",
        status_code=status.HTTP_201_CREATED,
        response_model=ApiResponse[out],  # type: ignore[valid-type]
        responses=error_responses(400, 401, 403, 409, 422),
    )
    def create_item(body: create, ctx: Creator, db: DbSession) -> dict:  # type: ignore[valid-type]
        return ok(service(db).create(ctx, body), f"{label} created successfully")

    @router.get(
        "/{item_id}",
        summary=f"Get a {lower}",
        response_model=ApiResponse[out],  # type: ignore[valid-type]
        responses=error_responses(401, 403, 404, 422),
    )
    def get_item(item_id: uuid.UUID, ctx: Viewer, db: DbSession) -> dict:
        return ok(service(db).get(item_id), f"{label} retrieved")

    @router.put(
        "/{item_id}",
        summary=f"Update a {lower}",
        description="Only the fields sent are changed.",
        response_model=ApiResponse[out],  # type: ignore[valid-type]
        responses=error_responses(400, 401, 403, 404, 409, 422),
    )
    def update_item(
        item_id: uuid.UUID,
        body: update,  # type: ignore[valid-type]
        ctx: Updater,
        db: DbSession,
    ) -> dict:
        return ok(service(db).update(ctx, item_id, body), f"{label} updated successfully")

    @router.delete(
        "/{item_id}",
        summary=f"Delete a {lower}",
        description="Refused if other records use it; deactivate it instead.",
        response_model=ApiResponse[None],
        responses=error_responses(401, 403, 404, 422),
    )
    def delete_item(item_id: uuid.UUID, ctx: Deleter, db: DbSession) -> dict:
        service(db).delete(ctx, item_id)
        return ok(None, f"{label} deleted")

    return router
