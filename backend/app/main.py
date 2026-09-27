"""Application factory: middleware, routers and exception handlers."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.middleware.request_context import (
    REQUEST_ID_HEADER,
    BodySizeLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.routers import (
    auth,
    finance,
    health,
    hr,
    inventory,
    organization,
    partners,
    procurement,
    roles,
    sales,
    system,
    users,
)
from app.utils.exceptions import AppError
from app.utils.logging import configure_logging

logger = logging.getLogger("app")

ROUTERS = [
    health.router,
    auth.router,
    users.router,
    roles.roles_router,
    roles.permissions_router,
    system.audit_router,
    system.notifications_router,
    organization.company_router,
    organization.branches_router,
    organization.departments_router,
    organization.settings_router,
    hr.employees_router,
    hr.leave_router,
    partners.customers_router,
    partners.suppliers_router,
    partners.categories_router,
    partners.products_router,
    inventory.warehouses_router,
    inventory.inventory_router,
    sales.router,
    procurement.router,
    finance.expense_categories_router,
    finance.router,
]

_HTTP_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    429: "RATE_LIMITED",
}


def _error(
    status_code: int,
    message: str,
    error_code: str,
    errors: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "message": message,
            "error_code": error_code,
            "errors": errors,
        },
        headers=headers,
    )


def _field_path(loc: tuple[Any, ...]) -> str | None:
    parts = [str(p) for p in loc if p not in ("body", "query", "path", "header", "cookie")]
    return ".".join(parts) or None


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return _error(exc.status_code, exc.message, exc.error_code, exc.errors, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = []
        for err in exc.errors():
            message = str(err.get("msg", "Invalid value"))
            if message.startswith("Value error, "):
                message = message.removeprefix("Value error, ")
            errors.append(
                {
                    "field": _field_path(tuple(err.get("loc", ()))),
                    "message": message,
                    "type": err.get("type"),
                }
            )
        return _error(422, "Validation failed", "VALIDATION_ERROR", errors)

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_ERROR_CODES.get(exc.status_code, "ERROR")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return _error(exc.status_code, message, code, headers=getattr(exc, "headers", None))

    @app.exception_handler(IntegrityError)
    async def integrity_handler(_: Request, exc: IntegrityError) -> JSONResponse:
        # Normally caught earlier by explicit checks; this covers races. No SQL is exposed.
        logger.warning("Integrity error: %s", type(exc.orig).__name__ if exc.orig else "unknown")
        return _error(409, "The request conflicts with existing data", "CONFLICT")

    @app.exception_handler(OperationalError)
    async def db_unavailable_handler(_: Request, exc: OperationalError) -> JSONResponse:
        logger.error("Database operational error: %s", type(exc.orig).__name__ if exc.orig else "")
        return _error(503, "The database is currently unavailable", "DATABASE_ERROR")

    @app.exception_handler(DBAPIError)
    async def dbapi_handler(_: Request, exc: DBAPIError) -> JSONResponse:
        if exc.connection_invalidated:
            return _error(503, "The database is currently unavailable", "DATABASE_ERROR")
        logger.exception("Database error")
        return _error(
            500, "An unexpected error occurred. Please try again later.", "INTERNAL_ERROR"
        )


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)

    docs = settings.DOCS_ENABLED
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "REST API for the Nyangu Holdings ERP (Zambia, ZMW, Africa/Lusaka).\n\n"
            "Log in with `POST /api/v1/auth/login`, then click **Authorize** and paste the "
            "`access_token`.\n\n"
            'Money amounts and quantities are decimals serialised as strings (e.g. `"1500.00"`) '
            "so no precision is lost."
        ),
        debug=settings.DEBUG,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json" if docs else None,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
    )

    # Middleware added last runs first (outermost).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER, "Retry-After"],
        max_age=600,
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.MAX_REQUEST_BODY_BYTES)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.ENVIRONMENT == "production")

    register_exception_handlers(app)

    prefix = settings.API_V1_PREFIX
    for router in ROUTERS:
        app.include_router(router, prefix=prefix)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, Any]:
        return {
            "success": True,
            "message": f"{settings.APP_NAME} API",
            "data": {"docs": "/docs" if docs else None, "health": f"{prefix}/health"},
        }

    return app


app = create_app()
