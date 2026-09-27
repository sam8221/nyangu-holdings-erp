"""Application settings, loaded from environment variables and the backend/.env file."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "testing", "staging", "production"]

# Values that must never be used as a signing key outside local development.
_PLACEHOLDER_SECRETS = {
    "",
    "change-this-in-production",
    "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET",
    "changeme",
    "secret",
}
MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # --- Application ---
    APP_NAME: str = "Nyangu Holdings ERP"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Environment = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"

    # --- Database ---
    DATABASE_URL: str
    TEST_DATABASE_URL: str | None = None

    # --- Security / JWT ---
    SECRET_KEY: str
    JWT_ALGORITHM: Literal["HS256"] = "HS256"
    JWT_ISSUER: str = "nyangu-erp"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=1, le=24 * 60)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, ge=1, le=90)

    # --- Login protection ---
    MAX_FAILED_LOGIN_ATTEMPTS: int = Field(default=5, ge=1)
    ACCOUNT_LOCKOUT_MINUTES: int = Field(default=15, ge=1)
    LOGIN_RATE_LIMIT_PER_MINUTE: int = Field(default=10, ge=1)

    # --- Password reset ---
    PASSWORD_RESET_EXPIRE_MINUTES: int = Field(default=30, ge=5, le=24 * 60)
    PASSWORD_RESET_RATE_LIMIT_PER_HOUR: int = Field(default=5, ge=1)

    # --- HTTP ---
    CORS_ORIGINS: str = "http://localhost:5173"
    FRONTEND_URL: str = "http://localhost:5173"
    MAX_REQUEST_BODY_BYTES: int = Field(default=2 * 1024 * 1024, ge=1024)
    DOCS_ENABLED: bool = True

    # --- Logging ---
    LOG_FORMAT: Literal["text", "json"] = "text"

    # --- Email ---
    # file: writes .eml files to EMAIL_FILE_DIR (development); smtp: real delivery;
    # console: logs a one-line summary only; memory: kept in-process (tests).
    EMAIL_BACKEND: Literal["file", "smtp", "console", "memory"] = "file"
    EMAIL_FROM: str = "Nyangu Holdings ERP <no-reply@nyanguholdings.com>"
    EMAIL_FILE_DIR: str = "var/outbox"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_USE_TLS: bool = True
    SMTP_TIMEOUT_SECONDS: int = Field(default=10, ge=1, le=120)

    # --- Localisation ---
    DEFAULT_CURRENCY: str = "ZMW"
    TIMEZONE: str = "Africa/Lusaka"

    # --- Seeding (development only) ---
    SEED_ADMIN_EMAIL: str | None = None
    SEED_ADMIN_PASSWORD: str | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production_like(self) -> bool:
        return self.ENVIRONMENT in ("staging", "production")

    @model_validator(mode="after")
    def _check_security(self) -> Settings:
        if self.ENVIRONMENT != "development":
            if self.SECRET_KEY in _PLACEHOLDER_SECRETS or len(self.SECRET_KEY) < MIN_SECRET_LENGTH:
                raise ValueError(
                    f"SECRET_KEY must be a random value of at least {MIN_SECRET_LENGTH} characters "
                    f"when ENVIRONMENT={self.ENVIRONMENT}"
                )
        if self.is_production_like and self.DEBUG:
            raise ValueError(f"DEBUG must be false when ENVIRONMENT={self.ENVIRONMENT}")
        if self.EMAIL_BACKEND == "smtp" and not self.SMTP_HOST:
            raise ValueError("SMTP_HOST is required when EMAIL_BACKEND=smtp")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
