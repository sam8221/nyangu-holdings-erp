"""Dashboard and reports."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Response

from app.auth.dependencies import DbSession, auth_with
from app.auth.permissions import Perm
from app.schemas.common import ApiResponse, error_responses, ok
from app.schemas.reports import DashboardOut, ReportInfo, ReportOut
from app.services.dashboard_service import DashboardService
from app.services.reports_service import (
    REPORTS,
    ReportParams,
    month_start,
    run_report,
    to_csv,
    to_xlsx,
)
from app.utils.exceptions import ForbiddenError
from app.utils.time import local_today

dashboard_router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
reports_router = APIRouter(prefix="/reports", tags=["Reports"])


@dashboard_router.get(
    "/summary",
    summary="Dashboard figures for the current user",
    description="Each section appears only if you may view that module. Pending approvals list "
    "only what you are allowed to approve.",
    response_model=ApiResponse[DashboardOut],
    responses=error_responses(401, 403),
)
def dashboard(ctx: auth_with(Perm.DASHBOARD_VIEW), db: DbSession) -> dict:
    return ok(DashboardService(db).summary(ctx), "Dashboard")


@reports_router.get(
    "",
    summary="Available reports",
    response_model=ApiResponse[list[ReportInfo]],
    responses=error_responses(401, 403),
)
def list_reports(ctx: auth_with(Perm.REPORTS_VIEW)) -> dict:
    data = [
        {
            "key": d.key,
            "title": d.title,
            "description": d.description,
            "uses_dates": d.uses_dates,
            "group_by_options": list(d.group_by_options),
        }
        for d in REPORTS.values()
    ]
    return ok(data, "Reports")


@reports_router.get(
    "/{report_key}",
    summary="Run a report",
    description="Dates default to the current month. `format=csv` or `format=xlsx` downloads "
    "the report and needs reports.export.",
    response_model=ApiResponse[ReportOut],
    responses={
        200: {
            "content": {
                "text/csv": {},
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {},
            },
            "description": "Report data (JSON) or a file download",
        },
        **error_responses(400, 401, 403, 404, 422),
    },
)
def get_report(
    ctx: auth_with(Perm.REPORTS_VIEW),
    db: DbSession,
    report_key: Annotated[str, Path(max_length=50)],
    date_from: date | None = None,
    date_to: date | None = None,
    group_by: str | None = None,
    format: Literal["json", "csv", "xlsx"] = "json",
) -> dict | Response:
    if format != "json" and not ctx.has(Perm.REPORTS_EXPORT):
        raise ForbiddenError("Exporting reports requires the reports.export permission")
    params = ReportParams(
        date_from=date_from or month_start(),
        date_to=date_to or local_today(),
        group_by=group_by,
    )
    result = run_report(db, report_key, params)
    if format == "json":
        return ok(result.as_dict(), result.title)
    stamp = local_today().isoformat()
    if format == "csv":
        return Response(
            to_csv(result),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{result.key}-{stamp}.csv"'},
        )
    return Response(
        to_xlsx(result),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{result.key}-{stamp}.xlsx"'},
    )
