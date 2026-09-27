"""Test fixtures.

Tests run against a real PostgreSQL database named by TEST_DATABASE_URL. The schema is built from
the Alembic migrations once per session, and every table is emptied before each test.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
os.chdir(BACKEND_DIR)  # so .env and alembic.ini resolve wherever pytest is launched from

# ---- Point the application at the test database *before* importing it -----------------------
from app.config import Settings  # noqa: E402  (class only; nothing is cached yet)

_base = Settings()  # type: ignore[call-arg]
if not _base.TEST_DATABASE_URL:
    raise RuntimeError("TEST_DATABASE_URL is not set. Add it to backend/.env (see README).")

_test_url = make_url(_base.TEST_DATABASE_URL)
_dev_url = make_url(_base.DATABASE_URL)
if _test_url.database == "nyangu_erp" or (
    _test_url.database == _dev_url.database
    and _test_url.host == _dev_url.host
    and _test_url.port == _dev_url.port
):
    raise RuntimeError(
        "Refusing to run: TEST_DATABASE_URL points at the main database. "
        "The test suite wipes its database before every test."
    )

os.environ["DATABASE_URL"] = _base.TEST_DATABASE_URL
os.environ["ENVIRONMENT"] = "testing"
os.environ["DEBUG"] = "false"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-0123456789abcdef"
os.environ["CORS_ORIGINS"] = "http://localhost:5173"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["EMAIL_BACKEND"] = "memory"
os.environ["FRONTEND_URL"] = "https://erp.example.com"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.auth.hashing import hash_password  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.middleware.rate_limit import login_rate_limiter, password_reset_rate_limiter  # noqa: E402
from app.models import Base, Role, User, UserStatus  # noqa: E402
from app.repositories.user_repository import UserRepository  # noqa: E402
from app.seed.catalog import seed_catalog  # noqa: E402
from app.services.email import memory_outbox  # noqa: E402

API = "/api/v1"
DEFAULT_PASSWORD = "Str0ng!Passw0rd"


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    """Recreate the schema from the real migrations once per test session."""
    url = _base.TEST_DATABASE_URL
    assert url
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def _clean_state() -> Iterator[None]:
    """Empty every table, re-seed the catalogue and reset in-memory state before each test."""
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with SessionLocal() as db:
        db.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        seed_catalog(db)
        db.commit()
    login_rate_limiter.reset()
    password_reset_rate_limiter.reset()
    memory_outbox().clear()
    yield


@pytest.fixture
def db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@dataclass
class TestUser:
    id: str
    email: str
    username: str
    password: str

    __test__ = False  # not a test class


@pytest.fixture
def make_user(db: Session) -> Callable[..., TestUser]:
    counter = {"n": 0}

    def _make(
        *roles: str,
        username: str | None = None,
        email: str | None = None,
        password: str = DEFAULT_PASSWORD,
        status: str = UserStatus.ACTIVE,
        full_name: str | None = None,
    ) -> TestUser:
        counter["n"] += 1
        username = username or f"user{counter['n']}"
        email = email or f"{username}@nyanguholdings.com"
        user = User(
            full_name=full_name or f"Test User {counter['n']}",
            username=username,
            email=email,
            password_hash=hash_password(password),
            status=status,
        )
        repo = UserRepository(db)
        repo.add(user)
        role_rows = [db.query(Role).filter_by(name=r).one() for r in roles]
        if role_rows:
            repo.replace_roles(user, [r.id for r in role_rows], None)
        db.commit()
        return TestUser(str(user.id), email, username, password)

    return _make


def login(client: TestClient, identifier: str, password: str = DEFAULT_PASSWORD) -> dict:
    response = client.post(
        f"{API}/auth/login", json={"identifier": identifier, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers(client: TestClient, make_user: Callable[..., TestUser]) -> Callable[..., dict]:
    """Create a user with the given roles, log in, and return Authorization headers."""

    def _headers(*roles: str, **kwargs) -> dict[str, str]:
        user = make_user(*roles, **kwargs)
        return bearer(login(client, user.email, user.password)["access_token"])

    return _headers


def role_id(db: Session, name: str) -> str:
    return str(db.query(Role).filter_by(name=name).one().id)
