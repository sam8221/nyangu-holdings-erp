"""Application exceptions. Each maps to one HTTP status and one error_code in the envelope."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code: int = 400
    error_code: str = "BAD_REQUEST"
    default_message: str = "Bad request"

    def __init__(
        self,
        message: str | None = None,
        *,
        errors: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.errors = errors
        self.headers = headers
        super().__init__(self.message)


class BadRequestError(AppError):
    status_code = 400
    error_code = "BAD_REQUEST"
    default_message = "Bad request"


class UnauthenticatedError(AppError):
    status_code = 401
    error_code = "UNAUTHENTICATED"
    default_message = "Authentication required"

    def __init__(self, message: str | None = None, **kwargs: Any) -> None:
        kwargs.setdefault("headers", {"WWW-Authenticate": "Bearer"})
        super().__init__(message, **kwargs)


class ForbiddenError(AppError):
    status_code = 403
    error_code = "FORBIDDEN"
    default_message = "You do not have permission to perform this action"


class NotFoundError(AppError):
    status_code = 404
    error_code = "NOT_FOUND"
    default_message = "Resource not found"


class ConflictError(AppError):
    status_code = 409
    error_code = "CONFLICT"
    default_message = "Resource already exists"


class BusinessRuleError(AppError):
    status_code = 422
    error_code = "BUSINESS_RULE_VIOLATION"
    default_message = "This action is not allowed"


class RateLimitedError(AppError):
    status_code = 429
    error_code = "RATE_LIMITED"
    default_message = "Too many requests. Please try again later."


class DatabaseUnavailableError(AppError):
    status_code = 503
    error_code = "DATABASE_ERROR"
    default_message = "The database is currently unavailable"
