"""Employees and leave management."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.auth.permissions import Perm
from app.models import User
from app.models.hr import Employee, EmployeeStatus, LeaveRequest, LeaveStatus
from app.models.organization import Branch, Department
from app.repositories.query import get_for_update_or_404, get_or_404, paginate, search_clause
from app.schemas.common import Page, PageParams
from app.schemas.hr import (
    SALARY_FIELDS,
    EmployeeCreate,
    EmployeeOut,
    EmployeeTerminate,
    EmployeeUpdate,
    LeaveRequestCreate,
)
from app.services.audit import AuditService, diff, snapshot
from app.services.auth_service import revoke_all_sessions
from app.services.base import (
    apply_changes,
    delete_or_block,
    ensure_unique,
    require_active,
    require_exists,
)
from app.services.notifications import NotificationService
from app.services.settings_service import SettingsService
from app.services.user_service import UserService
from app.utils.exceptions import BusinessRuleError, ForbiddenError
from app.utils.sequences import next_number
from app.utils.time import local_today, utcnow

_EMPLOYEE_FIELDS = tuple(
    f
    for f in EmployeeOut.model_fields
    if f not in {"id", "full_name", "branch", "department"} and not f.endswith("_at")
) + ("branch_id", "department_id")


def working_days(start: date, end: date) -> int:
    """Monday to Friday between two dates, inclusive."""
    days = 0
    current = start
    while current <= end:
        if current.weekday() < 5:
            days += 1
        current += timedelta(days=1)
    return days


class HRService:
    EMPLOYEE_SORT = {
        "employee_number": Employee.employee_number,
        "last_name": Employee.last_name,
        "first_name": Employee.first_name,
        "hire_date": Employee.hire_date,
        "status": Employee.status,
        "created_at": Employee.created_at,
    }
    LEAVE_SORT = {
        "start_date": LeaveRequest.start_date,
        "created_at": LeaveRequest.created_at,
        "status": LeaveRequest.status,
    }

    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.notifications = NotificationService(db)

    # ================================================================== employees
    @staticmethod
    def present(employee: Employee, ctx: AuthContext) -> EmployeeOut:
        out = EmployeeOut.model_validate(employee)
        if not ctx.has(Perm.EMPLOYEES_VIEW_SALARY):
            out = out.model_copy(update=dict.fromkeys(SALARY_FIELDS))
        return out

    def list_employees(
        self,
        ctx: AuthContext,
        params: PageParams,
        *,
        status: str | None,
        branch_id: uuid.UUID | None,
        department_id: uuid.UUID | None,
        employment_type: str | None,
    ) -> dict[str, Any]:
        stmt = select(Employee)
        if status:
            stmt = stmt.where(Employee.status == status)
        if branch_id:
            stmt = stmt.where(Employee.branch_id == branch_id)
        if department_id:
            stmt = stmt.where(Employee.department_id == department_id)
        if employment_type:
            stmt = stmt.where(Employee.employment_type == employment_type)
        if params.search:
            stmt = stmt.where(
                search_clause(
                    params.search,
                    Employee.first_name,
                    Employee.last_name,
                    Employee.employee_number,
                    Employee.email,
                    Employee.national_id,
                    Employee.job_title,
                )
            )
        items, total = paginate(
            self.db, stmt, params, self.EMPLOYEE_SORT, ("employee_number", "asc"), Employee.id
        )
        return Page.build([self.present(e, ctx) for e in items], total, params).model_dump()

    def get_employee(self, employee_id: uuid.UUID) -> Employee:
        return get_or_404(self.db, Employee, employee_id, "Employee")

    def _check_salary_permission(self, ctx: AuthContext, changes: dict[str, Any]) -> None:
        touched = [f for f in SALARY_FIELDS if changes.get(f) is not None]
        if touched and not ctx.has(Perm.EMPLOYEES_VIEW_SALARY):
            raise ForbiddenError(
                "Setting salary or bank details requires the employees.view_salary permission"
            )

    def _check_references(
        self, changes: dict[str, Any], employee_id: uuid.UUID | None = None
    ) -> None:
        if changes.get("branch_id"):
            require_active(
                require_exists(self.db, Branch, changes["branch_id"], "branch_id"), "branch_id"
            )
        if changes.get("department_id"):
            require_active(
                require_exists(self.db, Department, changes["department_id"], "department_id"),
                "department_id",
            )
        if changes.get("manager_id"):
            if changes["manager_id"] == employee_id:
                raise BusinessRuleError("An employee cannot be their own manager")
            manager = require_exists(self.db, Employee, changes["manager_id"], "manager_id")
            if manager.status == EmployeeStatus.TERMINATED:
                raise BusinessRuleError("The manager has been terminated")
        if changes.get("user_id"):
            require_exists(self.db, User, changes["user_id"], "user_id")
            ensure_unique(
                self.db,
                Employee,
                "user_id",
                changes["user_id"],
                exclude_id=employee_id,
                label="user account (already linked to another employee)",
            )
        for field, label in (("national_id", "national ID (NRC)"), ("email", "employee email")):
            ensure_unique(
                self.db, Employee, field, changes.get(field), exclude_id=employee_id, label=label
            )

    def create_employee(self, ctx: AuthContext, data: EmployeeCreate) -> Employee:
        values = data.model_dump()
        self._check_salary_permission(ctx, values)
        self._check_references(values)
        employee = Employee(
            **values,
            employee_number=next_number(self.db, "EMP", yearly=False),
            status=EmployeeStatus.ACTIVE,
        )
        self.db.add(employee)
        self.db.flush()
        self.audit.log(
            "employees.create",
            actor=ctx.user,
            entity_type="employee",
            entity_id=employee.id,
            summary=f"Created employee {employee.employee_number} {employee.full_name}",
            changes={
                k: v
                for k, v in snapshot(employee, _EMPLOYEE_FIELDS).items()
                if k not in SALARY_FIELDS
            },
        )
        self.db.commit()
        self.db.refresh(employee)
        return employee

    def update_employee(
        self, ctx: AuthContext, employee_id: uuid.UUID, data: EmployeeUpdate
    ) -> Employee:
        employee = get_for_update_or_404(self.db, Employee, employee_id, "Employee")
        if employee.status == EmployeeStatus.TERMINATED:
            raise BusinessRuleError("Terminated employees cannot be edited")
        changes = data.model_dump(exclude_unset=True)
        self._check_salary_permission(ctx, changes)
        self._check_references(changes, employee.id)
        new_hire = changes.get("hire_date")
        if new_hire and employee.termination_date and new_hire > employee.termination_date:
            raise BusinessRuleError("hire_date cannot be after the termination date")

        before = snapshot(employee, _EMPLOYEE_FIELDS)
        apply_changes(
            employee,
            changes,
            required=("first_name", "last_name", "employment_type", "hire_date", "status"),
        )
        delta = diff(before, snapshot(employee, _EMPLOYEE_FIELDS))
        if delta:
            # Salary values are sensitive: record that they changed, not what they are.
            for field in SALARY_FIELDS:
                if field in delta:
                    delta[field] = {"from": "***", "to": "***"}
            self.audit.log(
                "employees.update",
                actor=ctx.user,
                entity_type="employee",
                entity_id=employee.id,
                summary=f"Updated employee {employee.employee_number}",
                changes=delta,
            )
        self.db.commit()
        self.db.refresh(employee)
        return employee

    def terminate_employee(
        self, ctx: AuthContext, employee_id: uuid.UUID, data: EmployeeTerminate
    ) -> Employee:
        employee = get_for_update_or_404(self.db, Employee, employee_id, "Employee")
        if employee.status == EmployeeStatus.TERMINATED:
            raise BusinessRuleError("Employee is already terminated")
        if data.termination_date < employee.hire_date:
            raise BusinessRuleError("termination_date cannot be before the hire date")

        # A terminated employee must lose system access.
        if employee.user_id:
            user = self.db.get(User, employee.user_id)
            if user and user.is_active:
                if user.id == ctx.user.id:
                    raise BusinessRuleError("You cannot terminate your own employee record")
                users = UserService(self.db)
                users._guard_super_admin_target(ctx, user)
                users._guard_last_super_admin(user)
                user.status = "INACTIVE"
                revoke_all_sessions(self.db, user)
                self.audit.log(
                    "users.deactivate",
                    actor=ctx.user,
                    entity_type="user",
                    entity_id=user.id,
                    summary=f"Deactivated: employee {employee.employee_number} terminated",
                )

        employee.status = EmployeeStatus.TERMINATED
        employee.termination_date = data.termination_date
        employee.termination_reason = data.reason
        # Future leave no longer applies.
        for leave in self.db.scalars(
            select(LeaveRequest).where(
                LeaveRequest.employee_id == employee.id,
                LeaveRequest.status.in_(LeaveStatus.OPEN),
                LeaveRequest.start_date > data.termination_date,
            )
        ):
            leave.status = LeaveStatus.CANCELLED
        self.audit.log(
            "employees.terminate",
            actor=ctx.user,
            entity_type="employee",
            entity_id=employee.id,
            summary=f"Terminated employee {employee.employee_number}",
            changes={"termination_date": data.termination_date, "reason": data.reason},
        )
        self.db.commit()
        self.db.refresh(employee)
        return employee

    def delete_employee(self, ctx: AuthContext, employee_id: uuid.UUID) -> None:
        employee = self.get_employee(employee_id)
        number = employee.employee_number
        if self.db.scalar(select(func.count()).where(LeaveRequest.employee_id == employee.id)):
            raise BusinessRuleError(
                "This employee has leave history and cannot be deleted. Terminate them instead."
            )
        delete_or_block(self.db, employee, "employee")
        self.audit.log(
            "employees.delete",
            actor=ctx.user,
            entity_type="employee",
            entity_id=employee_id,
            summary=f"Deleted employee {number}",
        )
        self.db.commit()

    # ================================================================== leave
    def leave_balance(self, employee_id: uuid.UUID, year: int) -> dict[str, Any]:
        self.get_employee(employee_id)
        entitlement = Decimal(SettingsService(self.db).get("annual_leave_days"))
        rows = self.db.execute(
            select(LeaveRequest.status, func.coalesce(func.sum(LeaveRequest.days), 0))
            .where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.leave_type == "ANNUAL",
                LeaveRequest.status.in_(LeaveStatus.OPEN),
                func.extract("year", LeaveRequest.start_date) == year,
            )
            .group_by(LeaveRequest.status)
        ).all()
        totals = {status: Decimal(total) for status, total in rows}
        taken = totals.get(LeaveStatus.APPROVED, Decimal(0))
        pending = totals.get(LeaveStatus.PENDING, Decimal(0))
        return {
            "employee_id": employee_id,
            "year": year,
            "entitlement": entitlement,
            "taken": taken,
            "pending": pending,
            "remaining": entitlement - taken - pending,
        }

    def list_leave(
        self,
        params: PageParams,
        *,
        employee_id: uuid.UUID | None,
        status: str | None,
        leave_type: str | None,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        stmt = select(LeaveRequest).join(Employee, Employee.id == LeaveRequest.employee_id)
        if employee_id:
            stmt = stmt.where(LeaveRequest.employee_id == employee_id)
        if status:
            stmt = stmt.where(LeaveRequest.status == status)
        if leave_type:
            stmt = stmt.where(LeaveRequest.leave_type == leave_type)
        if date_from:
            stmt = stmt.where(LeaveRequest.end_date >= date_from)
        if date_to:
            stmt = stmt.where(LeaveRequest.start_date <= date_to)
        if params.search:
            stmt = stmt.where(
                search_clause(
                    params.search, Employee.first_name, Employee.last_name, Employee.employee_number
                )
            )
        items, total = paginate(
            self.db, stmt, params, self.LEAVE_SORT, ("start_date", "desc"), LeaveRequest.id
        )
        return Page.build(items, total, params).model_dump()

    def get_leave(self, leave_id: uuid.UUID) -> LeaveRequest:
        return get_or_404(self.db, LeaveRequest, leave_id, "Leave request")

    def create_leave(self, ctx: AuthContext, data: LeaveRequestCreate) -> LeaveRequest:
        employee = require_exists(self.db, Employee, data.employee_id, "employee_id")
        if employee.status == EmployeeStatus.TERMINATED:
            raise BusinessRuleError("Leave cannot be requested for a terminated employee")
        days = working_days(data.start_date, data.end_date)
        if days == 0:
            raise BusinessRuleError("The requested period contains no working days")

        overlap = self.db.scalar(
            select(func.count()).where(
                LeaveRequest.employee_id == employee.id,
                LeaveRequest.status.in_(LeaveStatus.OPEN),
                LeaveRequest.start_date <= data.end_date,
                LeaveRequest.end_date >= data.start_date,
            )
        )
        if overlap:
            raise BusinessRuleError(
                "This period overlaps another pending or approved leave request"
            )

        if data.leave_type == "ANNUAL":
            balance = self.leave_balance(employee.id, data.start_date.year)
            if Decimal(days) > balance["remaining"]:
                raise BusinessRuleError(
                    f"Not enough annual leave: {days} day(s) requested, "
                    f"{balance['remaining']} remaining for {data.start_date.year}"
                )

        leave = LeaveRequest(
            **data.model_dump(),
            days=Decimal(days),
            status=LeaveStatus.PENDING,
            created_by_id=ctx.user.id,
        )
        self.db.add(leave)
        self.db.flush()
        self.audit.log(
            "leave.create",
            actor=ctx.user,
            entity_type="leave_request",
            entity_id=leave.id,
            summary=f"{data.leave_type} leave for {employee.full_name}: "
            f"{data.start_date} to {data.end_date} ({days} days)",
        )
        self.notifications.notify_permission(
            Perm.LEAVE_APPROVE,
            "Leave request awaiting approval",
            f"{employee.full_name} requested {days} day(s) of {data.leave_type.lower()} leave "
            f"from {data.start_date} to {data.end_date}.",
            category="APPROVAL",
            entity_type="leave_request",
            entity_id=leave.id,
            exclude_user_id=ctx.user.id,
        )
        self.db.commit()
        self.db.refresh(leave)
        return leave

    def _decide(
        self, ctx: AuthContext, leave_id: uuid.UUID, status: str, comment: str | None
    ) -> LeaveRequest:
        leave = get_for_update_or_404(self.db, LeaveRequest, leave_id, "Leave request")
        if leave.status != LeaveStatus.PENDING:
            raise BusinessRuleError(
                f"Only pending requests can be decided (this one is {leave.status})"
            )
        if leave.employee.user_id == ctx.user.id:
            raise BusinessRuleError("You cannot approve or reject your own leave request")
        leave.status = status
        leave.reviewed_by_id = ctx.user.id
        leave.reviewed_at = utcnow()
        leave.review_comment = comment
        approved = status == LeaveStatus.APPROVED
        verb = "approved" if approved else "rejected"
        self.audit.log(
            "leave.approve" if approved else "leave.reject",
            actor=ctx.user,
            entity_type="leave_request",
            entity_id=leave.id,
            summary=f"Leave for {leave.employee.full_name} {verb}",
            changes={"status": {"from": LeaveStatus.PENDING, "to": status}, "comment": comment},
        )
        self.notifications.notify(
            [uid for uid in (leave.created_by_id, leave.employee.user_id) if uid],
            f"Leave request {verb}",
            f"The {leave.leave_type.lower()} leave from {leave.start_date} to {leave.end_date} "
            f"for {leave.employee.full_name} was {verb}."
            + (f" Comment: {comment}" if comment else ""),
            category="SUCCESS" if status == LeaveStatus.APPROVED else "INFO",
            entity_type="leave_request",
            entity_id=leave.id,
        )
        self.db.commit()
        self.db.refresh(leave)
        return leave

    def approve_leave(
        self, ctx: AuthContext, leave_id: uuid.UUID, comment: str | None
    ) -> LeaveRequest:
        return self._decide(ctx, leave_id, LeaveStatus.APPROVED, comment)

    def reject_leave(self, ctx: AuthContext, leave_id: uuid.UUID, comment: str) -> LeaveRequest:
        return self._decide(ctx, leave_id, LeaveStatus.REJECTED, comment)

    def cancel_leave(self, ctx: AuthContext, leave_id: uuid.UUID) -> LeaveRequest:
        leave = get_for_update_or_404(self.db, LeaveRequest, leave_id, "Leave request")
        if leave.status == LeaveStatus.PENDING:
            pass
        elif leave.status == LeaveStatus.APPROVED:
            if leave.start_date <= local_today():
                raise BusinessRuleError(
                    "Approved leave that has already started cannot be cancelled"
                )
        else:
            raise BusinessRuleError(f"A {leave.status.lower()} request cannot be cancelled")
        previous = leave.status
        leave.status = LeaveStatus.CANCELLED
        self.audit.log(
            "leave.cancel",
            actor=ctx.user,
            entity_type="leave_request",
            entity_id=leave.id,
            summary=f"Leave for {leave.employee.full_name} cancelled",
            changes={"status": {"from": previous, "to": LeaveStatus.CANCELLED}},
        )
        self.db.commit()
        self.db.refresh(leave)
        return leave
