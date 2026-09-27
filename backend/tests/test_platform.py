"""Platform behaviour: health, docs, headers, CORS, error envelope, configuration safety."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import get_db
from app.main import app
from app.utils.logging import SensitiveDataFilter, mask_sensitive
from tests.conftest import API


def test_health_ok(client: TestClient) -> None:
    r = client.get(f"{API}/health")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"
    assert body["data"]["database"] == "ok"


def test_health_reports_503_when_database_is_down(client: TestClient) -> None:
    dead = create_engine(
        "postgresql+psycopg://nobody:nothing@127.0.0.1:1/none", connect_args={"connect_timeout": 2}
    )
    DeadSession = sessionmaker(bind=dead)

    def broken_db():
        with DeadSession() as s:
            yield s

    app.dependency_overrides[get_db] = broken_db
    try:
        r = client.get(f"{API}/health")
    finally:
        app.dependency_overrides.pop(get_db, None)
        dead.dispose()
    assert r.status_code == 503
    assert r.json()["error_code"] == "DATABASE_ERROR"
    assert "nobody" not in r.text and "psycopg" not in r.text


def test_docs_and_openapi_available(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    spec = client.get(f"{API}/openapi.json")
    assert spec.status_code == 200
    assert spec.json()["info"]["title"] == "Nyangu Holdings ERP"


def test_every_endpoint_is_documented(client: TestClient) -> None:
    spec = client.get(f"{API}/openapi.json").json()
    assert "HTTPBearer" in spec["components"]["securitySchemes"]
    operations = [
        (path, method, op) for path, ops in spec["paths"].items() for method, op in ops.items()
    ]
    assert len(operations) >= 19
    for path, method, op in operations:
        assert path.startswith(API), path
        assert op.get("summary"), f"{method.upper()} {path} has no summary"
        assert op.get("tags"), f"{method.upper()} {path} has no tag"
        success = next(c for c in op["responses"] if c.startswith("2"))
        assert "content" in op["responses"][success], f"{method.upper()} {path} has no schema"


def test_security_headers_present(client: TestClient) -> None:
    r = client.get(f"{API}/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["Cache-Control"] == "no-store"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert "Strict-Transport-Security" not in r.headers  # production only


def test_request_id_generated_and_echoed(client: TestClient) -> None:
    generated = client.get(f"{API}/health").headers["X-Request-ID"]
    assert len(generated) == 32
    echoed = client.get(f"{API}/health", headers={"X-Request-ID": "abc-123"})
    assert echoed.headers["X-Request-ID"] == "abc-123"
    unsafe = client.get(f"{API}/health", headers={"X-Request-ID": "bad id\twith spaces"})
    assert unsafe.headers["X-Request-ID"] != "bad id\twith spaces"


def test_cors_allows_configured_origin(client: TestClient) -> None:
    r = client.options(
        f"{API}/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_rejects_unknown_origin(client: TestClient) -> None:
    r = client.get(f"{API}/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in r.headers
    preflight = client.options(
        f"{API}/auth/login",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"},
    )
    assert preflight.status_code == 400


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    r = client.get(f"{API}/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {
        "success": False,
        "message": "Not Found",
        "error_code": "NOT_FOUND",
        "errors": None,
    }


def test_validation_error_envelope(client: TestClient) -> None:
    r = client.post(f"{API}/auth/login", json={"identifier": "", "extra": 1})
    assert r.status_code == 422
    body = r.json()
    assert body["success"] is False
    assert body["error_code"] == "VALIDATION_ERROR"
    fields = {e["field"] for e in body["errors"]}
    assert {"identifier", "password", "extra"} <= fields


def test_unhandled_error_returns_safe_500() -> None:
    path = f"{API}/__test_boom__"
    if not any(getattr(r, "path", None) == path for r in app.router.routes):

        @app.get(path, include_in_schema=False)
        def boom() -> None:
            raise RuntimeError("secret internal detail SELECT * FROM users")

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get(path)
    assert r.status_code == 500
    assert r.json()["error_code"] == "INTERNAL_ERROR"
    assert "secret internal detail" not in r.text
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "X-Request-ID" in r.headers


def _settings(**overrides) -> Settings:
    base = {"DATABASE_URL": "postgresql+psycopg://u:p@localhost/db", "_env_file": None}
    return Settings(**{**base, **overrides})  # type: ignore[arg-type]


def test_production_refuses_weak_secret_key() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        _settings(ENVIRONMENT="production", SECRET_KEY="short")
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        _settings(ENVIRONMENT="staging", SECRET_KEY="change-this-in-production")
    ok = _settings(ENVIRONMENT="production", SECRET_KEY="x" * 48)
    assert ok.ENVIRONMENT == "production"


def test_production_refuses_debug() -> None:
    with pytest.raises(ValidationError, match="DEBUG"):
        _settings(ENVIRONMENT="production", SECRET_KEY="x" * 48, DEBUG=True)


def test_logs_mask_passwords_and_tokens() -> None:
    assert "hunter2" not in mask_sensitive('{"password": "hunter2"}')
    assert "abc.def.ghi" not in mask_sensitive("Authorization: Bearer abc.def.ghi")
    assert "eyJhbGciOi" not in mask_sensitive("token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig")
    assert "$argon2id$v=19" not in mask_sensitive("hash=$argon2id$v=19$m=65536,t=3,p=4$abc$def")

    record = logging.LogRecord(
        "t", logging.INFO, __file__, 1, "login password=%s", ("S3cret!",), None
    )
    SensitiveDataFilter().filter(record)
    assert "S3cret!" not in record.getMessage()


def test_oversized_request_body_is_rejected(client: TestClient) -> None:
    from app.config import get_settings

    limit = get_settings().MAX_REQUEST_BODY_BYTES
    r = client.post(
        f"{API}/auth/login",
        content=b"x" * (limit + 1),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 413
    assert r.json()["error_code"] == "PAYLOAD_TOO_LARGE"


def test_json_log_format() -> None:
    import json

    from app.utils.logging import JsonFormatter

    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    record.request_id = "abc"
    line = json.loads(JsonFormatter().format(record))
    assert line["message"] == "hello world" and line["request_id"] == "abc"
