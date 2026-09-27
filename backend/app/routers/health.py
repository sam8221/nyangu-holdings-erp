"""Health check."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.auth.dependencies import DbSession
from app.config import get_settings
from app.schemas.common import ApiResponse, error_responses, ok
from app.utils.exceptions import DatabaseUnavailableError
from app.utils.time import utcnow

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])


class HealthOut(BaseModel):
    status: str
    app: str
    version: str
    environment: str
    database: str
    timestamp: str


@router.get(
    "/health",
    summary="API and database health",
    response_model=ApiResponse[HealthOut],
    responses=error_responses(503),
)
def health(db: DbSession) -> dict:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.error("Health check: database unreachable (%s)", type(exc).__name__)
        raise DatabaseUnavailableError() from exc
    s = get_settings()
    return ok(
        {
            "status": "ok",
            "app": s.APP_NAME,
            "version": s.APP_VERSION,
            "environment": s.ENVIRONMENT,
            "database": "ok",
            "timestamp": utcnow().isoformat(),
        },
        "Service is healthy",
    )
