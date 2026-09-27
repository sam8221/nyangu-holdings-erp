"""Audit log and notification endpoints."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.auth.dependencies import AuthContext, DbSession, require_permissions
from app.auth.permissions import Perm
from app.models.system import AuditLog
from app.repositories.query import get_or_404, paginate, search_clause
from app.schemas.common import ApiResponse, Page, PageParams, error_responses, ok, page_params
from app.schemas.system import AuditLogOut, MarkedRead, NotificationOut, UnreadCount
from app.services.notifications import NotificationService
from app.utils.time import start_of_local_day

audit_router = APIRouter(prefix="/audit-logs", tags=["Audit logs"])
notifications_router = APIRouter(prefix="/notifications", tags=["Notifications"])

AuditViewer = Annotated[AuthContext, Depends(require_permissions(Perm.AUDIT_VIEW))]
NotificationReader = Annotated[AuthContext, Depends(require_permissions(Perm.NOTIFICATIONS_VIEW))]

_AUDIT_SORT = {"occurred_at": AuditLog.occurred_at, "action": AuditLog.action}


@audit_router.get(
    "",
    summary="Search the audit log",
    description="Filter by actor, action (prefix match, e.g. `users.`), entity and date range. "
    "Dates are interpreted in the business timezone.",
    response_model=ApiResponse[Page[AuditLogOut]],
    responses=error_responses(400, 401, 403, 422),
)
def list_audit_logs(
    ctx: AuditViewer,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    actor_id: uuid.UUID | None = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    entity_type: Annotated[str | None, Query(max_length=50)] = None,
    entity_id: Annotated[str | None, Query(max_length=64)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    stmt = select(AuditLog)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if action:
        stmt = stmt.where(AuditLog.action.startswith(action.lower(), autoescape=True))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type.lower())
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if date_from:
        stmt = stmt.where(AuditLog.occurred_at >= start_of_local_day(date_from))
    if date_to:
        stmt = stmt.where(AuditLog.occurred_at < start_of_local_day(date_to + timedelta(days=1)))
    if params.search:
        stmt = stmt.where(search_clause(params.search, AuditLog.summary, AuditLog.actor_label))
    items, total = paginate(db, stmt, params, _AUDIT_SORT, ("occurred_at", "desc"), AuditLog.id)
    return ok(Page.build(items, total, params).model_dump(), "Audit log retrieved")


@audit_router.get(
    "/{entry_id}",
    summary="Get one audit log entry",
    response_model=ApiResponse[AuditLogOut],
    responses=error_responses(401, 403, 404, 422),
)
def get_audit_log(entry_id: uuid.UUID, ctx: AuditViewer, db: DbSession) -> dict:
    return ok(get_or_404(db, AuditLog, entry_id, "Audit log entry"), "Audit log entry retrieved")


@notifications_router.get(
    "",
    summary="Your notifications",
    response_model=ApiResponse[Page[NotificationOut]],
    responses=error_responses(400, 401, 403, 422),
)
def list_notifications(
    ctx: NotificationReader,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    unread_only: bool = False,
) -> dict:
    data = NotificationService(db).list_for_user(ctx.user.id, params, unread_only)
    return ok(data, "Notifications retrieved")


@notifications_router.get(
    "/unread-count",
    summary="Number of unread notifications",
    response_model=ApiResponse[UnreadCount],
    responses=error_responses(401, 403),
)
def unread_count(ctx: NotificationReader, db: DbSession) -> dict:
    return ok({"unread": NotificationService(db).unread_count(ctx.user.id)}, "Unread count")


@notifications_router.post(
    "/read-all",
    summary="Mark all your notifications as read",
    response_model=ApiResponse[MarkedRead],
    responses=error_responses(401, 403),
)
def mark_all_read(ctx: NotificationReader, db: DbSession) -> dict:
    updated = NotificationService(db).mark_all_read(ctx.user.id)
    return ok({"updated": updated}, "Notifications marked as read")


@notifications_router.post(
    "/{notification_id}/read",
    summary="Mark one notification as read",
    response_model=ApiResponse[NotificationOut],
    responses=error_responses(401, 403, 404, 422),
)
def mark_read(notification_id: uuid.UUID, ctx: NotificationReader, db: DbSession) -> dict:
    note = NotificationService(db).mark_read(ctx.user.id, notification_id)
    return ok(note, "Notification marked as read")
