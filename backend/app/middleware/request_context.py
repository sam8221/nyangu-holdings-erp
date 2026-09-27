"""Request ID, access logging, catch-all error handling and security headers (pure ASGI)."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.utils.logging import request_id_ctx

logger = logging.getLogger("app.request")

_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9\-_.]{1,64}$")
REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware:
    """Assigns an X-Request-ID, logs each request, and turns unhandled errors into a safe 500."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = next(
            (v.decode("latin-1") for k, v in scope["headers"] if k == b"x-request-id"), ""
        )
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_ctx.set(request_id)
        scope.setdefault("state", {})["request_id"] = request_id

        start = time.perf_counter()
        status_holder = {"status": 500, "started": False}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                status_holder["started"] = True
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception("Unhandled error on %s %s", scope["method"], scope["path"])
            if status_holder["started"]:
                raise
            body = json.dumps(
                {
                    "success": False,
                    "message": "An unexpected error occurred. Please try again later.",
                    "error_code": "INTERNAL_ERROR",
                    "errors": None,
                }
            ).encode()
            await send_wrapper(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "%s %s -> %s (%.1f ms)",
                scope["method"],
                scope["path"],
                status_holder["status"],
                duration_ms,
            )
            request_id_ctx.reset(token)


_DOCS_PATHS = ("/docs", "/redoc")
_API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
_DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.redoc.ly; "
    "worker-src 'self' blob:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool = False) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        is_docs = scope["path"].startswith(_DOCS_PATHS)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                headers["Cross-Origin-Opener-Policy"] = "same-origin"
                headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
                headers["Content-Security-Policy"] = _DOCS_CSP if is_docs else _API_CSP
                headers["Cache-Control"] = "no-store"
                if self.hsts:
                    headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
            await send(message)

        await self.app(scope, receive, send_wrapper)
