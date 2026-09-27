"""Password hashing with Argon2id."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import get_settings


def _build_hasher() -> PasswordHasher:
    if get_settings().ENVIRONMENT == "testing":
        # Cheap parameters keep the test suite fast. Never used outside tests.
        return PasswordHasher(time_cost=1, memory_cost=8 * 1024, parallelism=1)
    # argon2-cffi defaults follow RFC 9106 "low memory" recommendations (Argon2id).
    return PasswordHasher()


_hasher = _build_hasher()

# Verified against when a login names an unknown account, so that response time does not reveal
# whether the account exists.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing-equalisation")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def verify_dummy_password(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True
