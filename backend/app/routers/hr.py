"""Employees and leave requests."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.auth.dependencies import DbSession, auth_with
from app.auth.permissions import Perm
from app.schemas.common import ApiResponse, Page, PageParams, error_responses, ok, page_params
from app.schemas.hr import (
    EmployeeCreate,
    EmployeeOut,
    EmployeeStatusLiteral,
    EmployeeTerminate,
    EmployeeUpdate,
    EmploymentType,
    LeaveBalance,
    LeaveDecision,
    LeaveRejection,
    LeaveRequestCreate,
    LeaveRequestOut,
    LeaveStatusLiteral,
    LeaveType,
)
from app.services.hr_service import HRService
from app.utils.time import local_today

employees_router = APIRouter(prefix="/employees", tags=["Employees"])
leave_router = APIRouter(prefix="/leave-requests", tags=["Leave"])

Params = Annotated[PageParams, Depends(page_params)]
_E = (401, 403, 422)


# ---------------------------------------------------------------------- employees
@employees_router.get(
    "",
    summary="List employees",
    description="Salary and bank fields are null unless you hold employees.view_salary. "
    "Sort: employee_number, last_name, first_name, hire_date, status, created_at.",
    response_model=ApiResponse[Page[EmployeeOut]],
    responses=error_responses(400, *_E),
)
def list_employees(
    ctx: auth_with(Perm.EMPLOYEES_VIEW),
    db: DbSession,
    params: Params,
    status_: Annotated[EmployeeStatusLiteral | None, Query(alias="status")] = None,
    branch_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    employment_type: EmploymentType | None = None,
) -> dict:
    data = HRService(db).list_employees(
        ctx,
        params,
        status=status_,
        branch_id=branch_id,
        department_id=department_id,
        employment_type=employment_type,
    )
    return ok(data, "Employees retrieved")


@employees_router.post(
    "",
    summary="Create an employee",
    description="The employee number is generated. Salary and bank details need "
    "employees.view_salary.",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[EmployeeOut],
    responses=error_responses(400, 409, *_E),
)
def create_employee(
    body: EmployeeCreate, ctx: auth_with(Perm.EMPLOYEES_CREATE), db: DbSession
) -> dict:
    service = HRService(db)
    return ok(service.present(service.create_employee(ctx, body), ctx), "Employee created")


@employees_router.get(
    "/{employee_id}",
    summary="Get an employee",
    response_model=ApiResponse[EmployeeOut],
    responses=error_responses(404, *_E),
)
def get_employee(
    employee_id: uuid.UUID, ctx: auth_with(Perm.EMPLOYEES_VIEW), db: DbSession
) -> dict:
    service = HRService(db)
    return ok(service.present(service.get_employee(employee_id), ctx), "Employee retrieved")


@employees_router.put(
    "/{employee_id}",
    summary="Update an employee",
    response_model=ApiResponse[EmployeeOut],
    responses=error_responses(400, 404, 409, *_E),
)
def update_employee(
    employee_id: uuid.UUID,
    body: EmployeeUpdate,
    ctx: auth_with(Perm.EMPLOYEES_UPDATE),
    db: DbSession,
) -> dict:
    service = HRService(db)
    employee = service.update_employee(ctx, employee_id, body)
    return ok(service.present(employee, ctx), "Employee updated")


@employees_router.post(
    "/{employee_id}/terminate",
    summary="Terminate an employee",
    description="Also deactivates the linked user account and cancels future leave.",
    response_model=ApiResponse[EmployeeOut],
    responses=error_responses(404, *_E),
)
def terminate_employee(
    employee_id: uuid.UUID,
    body: EmployeeTerminate,
    ctx: auth_with(Perm.EMPLOYEES_UPDATE),
    db: DbSession,
) -> dict:
    service = HRService(db)
    employee = service.terminate_employee(ctx, employee_id, body)
    return ok(service.present(employee, ctx), "Employee terminated")


@employees_router.delete(
    "/{employee_id}",
    summary="Delete an employee with no history",
    response_model=ApiResponse[None],
    responses=error_responses(404, *_E),
)
def delete_employee(
    employee_id: uuid.UUID, ctx: auth_with(Perm.EMPLOYEES_DELETE), db: DbSession
) -> dict:
    HRService(db).delete_employee(ctx, employee_id)
    return ok(None, "Employee deleted")


@employees_router.get(
    "/{employee_id}/leave-balance",
    summary="Annual leave balance",
    response_model=ApiResponse[LeaveBalance],
    responses=error_responses(404, *_E),
)
def leave_balance(
    employee_id: uuid.UUID,
    ctx: auth_with(Perm.LEAVE_VIEW),
    db: DbSession,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
) -> dict:
    data = HRService(db).leave_balance(employee_id, year or local_today().year)
    return ok(data, "Leave balance")


# ---------------------------------------------------------------------- leave
@leave_router.get(
    "",
    summary="List leave requests",
    description="date_from/date_to return requests overlapping that period. "
    "Sort: start_date, created_at, status.",
    response_model=ApiResponse[Page[LeaveRequestOut]],
    responses=error_responses(400, *_E),
)
def list_leave(
    ctx: auth_with(Perm.LEAVE_VIEW),
    db: DbSession,
    params: Params,
    employee_id: uuid.UUID | None = None,
    status_: Annotated[LeaveStatusLiteral | None, Query(alias="status")] = None,
    leave_type: LeaveType | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    data = HRService(db).list_leave(
        params,
        employee_id=employee_id,
        status=status_,
        leave_type=leave_type,
        date_from=date_from,
        date_to=date_to,
    )
    return ok(data, "Leave requests retrieved")


@leave_router.post(
    "",
    summary="Request leave",
    description="Days are counted Monday to Friday. Annual leave is checked against the balance. "
    "Approvers are notified.",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[LeaveRequestOut],
    responses=error_responses(400, *_E),
)
def create_leave(
    body: LeaveRequestCreate, ctx: auth_with(Perm.LEAVE_CREATE), db: DbSession
) -> dict:
    return ok(HRService(db).create_leave(ctx, body), "Leave request submitted")


@leave_router.get(
    "/{leave_id}",
    summary="Get a leave request",
    response_model=ApiResponse[LeaveRequestOut],
    responses=error_responses(404, *_E),
)
def get_leave(leave_id: uuid.UUID, ctx: auth_with(Perm.LEAVE_VIEW), db: DbSession) -> dict:
    return ok(HRService(db).get_leave(leave_id), "Leave request retrieved")


@leave_router.post(
    "/{leave_id}/approve",
    summary="Approve a pending leave request",
    response_model=ApiResponse[LeaveRequestOut],
    responses=error_responses(404, *_E),
)
def approve_leave(
    leave_id: uuid.UUID,
    ctx: auth_with(Perm.LEAVE_APPROVE),
    db: DbSession,
    body: LeaveDecision | None = None,
) -> dict:
    comment = body.comment if body else None
    return ok(HRService(db).approve_leave(ctx, leave_id, comment), "Leave request approved")


@leave_router.post(
    "/{leave_id}/reject",
    summary="Reject a pending leave request",
    response_model=ApiResponse[LeaveRequestOut],
    responses=error_responses(404, *_E),
)
def reject_leave(
    leave_id: uuid.UUID, body: LeaveRejection, ctx: auth_with(Perm.LEAVE_APPROVE), db: DbSession
) -> dict:
    return ok(HRService(db).reject_leave(ctx, leave_id, body.comment), "Leave request rejected")


@leave_router.post(
    "/{leave_id}/cancel",
    summary="Cancel a pending, or future approved, leave request",
    response_model=ApiResponse[LeaveRequestOut],
    responses=error_responses(404, *_E),
)
def cancel_leave(leave_id: uuid.UUID, ctx: auth_with(Perm.LEAVE_CREATE), db: DbSession) -> dict:
    return ok(HRService(db).cancel_leave(ctx, leave_id), "Leave request cancelled")
