"""Response envelope, error format and pagination primitives shared by every endpoint."""

from __future__ import annotations

import math
from typing import Annotated, Any, Generic, Literal, TypeVar

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

MAX_PAGE_SIZE = 100


class ApiResponse(BaseModel, Generic[T]):
    """Envelope for every successful response."""

    success: Literal[True] = True
    message: str
    data: T | None = None


class ErrorDetail(BaseModel):
    field: str | None = None
    message: str
    type: str | None = None


class ErrorResponse(BaseModel):
    """Envelope for every error response."""

    success: Literal[False] = False
    message: str
    error_code: str
    errors: list[ErrorDetail] | None = None


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class Page(BaseModel, Generic[T]):
    items: list[T]
    meta: PageMeta

    @classmethod
    def build(cls, items: list[Any], total: int, params: PageParams) -> Page[T]:
        return cls(
            items=items,
            meta=PageMeta(
                page=params.page,
                page_size=params.page_size,
                total=total,
                pages=math.ceil(total / params.page_size) if total else 0,
            ),
        )


class PageParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    page: int = 1
    page_size: int = 20
    search: str | None = None
    sort_by: str | None = None
    sort_order: Literal["asc", "desc"] | None = None

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: Annotated[int, Query(ge=1, description="Page number, starting at 1")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=MAX_PAGE_SIZE, description="Items per page (max 100)")
    ] = 20,
    search: Annotated[
        str | None, Query(max_length=100, description="Case-insensitive text search")
    ] = None,
    sort_by: Annotated[str | None, Query(max_length=50, description="Field to sort by")] = None,
    sort_order: Annotated[Literal["asc", "desc"] | None, Query(description="asc or desc")] = None,
) -> PageParams:
    search = search.strip() if search else None
    return PageParams(
        page=page,
        page_size=page_size,
        search=search or None,
        sort_by=sort_by,
        sort_order=sort_order,
    )


def ok(data: Any = None, message: str = "Success") -> dict[str, Any]:
    """Build a success envelope; FastAPI validates it against the route's response_model."""
    return {"success": True, "message": message, "data": data}


# Error responses documented on every route in OpenAPI.
def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    descriptions = {
        400: "Bad request",
        401: "Not authenticated",
        403: "Not permitted",
        404: "Not found",
        409: "Conflict",
        422: "Validation failed or business rule violated",
        429: "Rate limited",
        503: "Database unavailable",
    }
    return {c: {"model": ErrorResponse, "description": descriptions[c]} for c in codes}


NonEmptyStr = Annotated[str, Field(min_length=1)]
