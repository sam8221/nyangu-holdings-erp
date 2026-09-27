"""Company profile, branches and departments."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.models.organization import Branch, Company, Department
from app.repositories.query import get_or_404, paginate, search_clause
from app.schemas.common import Page, PageParams
from app.schemas.organization import (
    BranchCreate,
    BranchUpdate,
    CompanyUpdate,
    DepartmentCreate,
    DepartmentUpdate,
)
from app.services.audit import AuditService, diff, snapshot
from app.services.base import apply_changes, delete_or_block, ensure_unique
from app.utils.exceptions import NotFoundError

_COMPANY_FIELDS = tuple(CompanyUpdate.model_fields)
_BRANCH_FIELDS = (*BranchUpdate.model_fields,)
_DEPARTMENT_FIELDS = (*DepartmentUpdate.model_fields,)


class OrganizationService:
    BRANCH_SORT = {"code": Branch.code, "name": Branch.name, "created_at": Branch.created_at}
    DEPARTMENT_SORT = {
        "code": Department.code,
        "name": Department.name,
        "created_at": Department.created_at,
    }

    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    # ------------------------------------------------------------------ company
    def company(self) -> Company:
        company = self.db.scalars(select(Company).limit(1)).first()
        if company is None:
            raise NotFoundError("Company profile has not been set up. Run the seed script.")
        return company

    def update_company(self, ctx: AuthContext, data: CompanyUpdate) -> Company:
        company = self.company()
        before = snapshot(company, _COMPANY_FIELDS)
        apply_changes(
            company,
            data.model_dump(exclude_unset=True),
            required=("name", "country", "currency", "fiscal_year_start_month"),
        )
        self._log("company.update", ctx, company, "company", before, _COMPANY_FIELDS)
        self.db.commit()
        self.db.refresh(company)
        return company

    # ------------------------------------------------------------------ branches
    def list_branches(self, params: PageParams, active: bool | None) -> dict[str, Any]:
        stmt = select(Branch)
        if active is not None:
            stmt = stmt.where(Branch.is_active.is_(active))
        if params.search:
            stmt = stmt.where(search_clause(params.search, Branch.code, Branch.name, Branch.city))
        items, total = paginate(self.db, stmt, params, self.BRANCH_SORT, ("code", "asc"), Branch.id)
        return Page.build(items, total, params).model_dump()

    def get_branch(self, branch_id: uuid.UUID) -> Branch:
        return get_or_404(self.db, Branch, branch_id, "Branch")

    def _single_head_office(self, keep: Branch) -> None:
        self.db.execute(update(Branch).where(Branch.id != keep.id).values(is_head_office=False))

    def create_branch(self, ctx: AuthContext, data: BranchCreate) -> Branch:
        ensure_unique(self.db, Branch, "code", data.code, label="branch code")
        branch = Branch(**data.model_dump())
        self.db.add(branch)
        self.db.flush()
        if branch.is_head_office:
            self._single_head_office(branch)
        self.audit.log(
            "branches.create",
            actor=ctx.user,
            entity_type="branch",
            entity_id=branch.id,
            summary=f"Created branch {branch.code}",
            changes=snapshot(branch, _BRANCH_FIELDS),
        )
        self.db.commit()
        self.db.refresh(branch)
        return branch

    def update_branch(self, ctx: AuthContext, branch_id: uuid.UUID, data: BranchUpdate) -> Branch:
        branch = self.get_branch(branch_id)
        changes = data.model_dump(exclude_unset=True)
        ensure_unique(
            self.db, Branch, "code", changes.get("code"), exclude_id=branch.id, label="branch code"
        )
        before = snapshot(branch, _BRANCH_FIELDS)
        apply_changes(branch, changes, required=("code", "name", "is_head_office", "is_active"))
        if branch.is_head_office:
            self._single_head_office(branch)
        self._log("branches.update", ctx, branch, "branch", before, _BRANCH_FIELDS)
        self.db.commit()
        self.db.refresh(branch)
        return branch

    def delete_branch(self, ctx: AuthContext, branch_id: uuid.UUID) -> None:
        branch = self.get_branch(branch_id)
        code = branch.code
        delete_or_block(self.db, branch, "branch")
        self.audit.log(
            "branches.delete",
            actor=ctx.user,
            entity_type="branch",
            entity_id=branch_id,
            summary=f"Deleted branch {code}",
        )
        self.db.commit()

    # ------------------------------------------------------------------ departments
    def list_departments(self, params: PageParams, active: bool | None) -> dict[str, Any]:
        stmt = select(Department)
        if active is not None:
            stmt = stmt.where(Department.is_active.is_(active))
        if params.search:
            stmt = stmt.where(search_clause(params.search, Department.code, Department.name))
        items, total = paginate(
            self.db, stmt, params, self.DEPARTMENT_SORT, ("name", "asc"), Department.id
        )
        return Page.build(items, total, params).model_dump()

    def get_department(self, department_id: uuid.UUID) -> Department:
        return get_or_404(self.db, Department, department_id, "Department")

    def create_department(self, ctx: AuthContext, data: DepartmentCreate) -> Department:
        ensure_unique(self.db, Department, "code", data.code, label="department code")
        ensure_unique(self.db, Department, "name", data.name, label="department name")
        department = Department(**data.model_dump())
        self.db.add(department)
        self.db.flush()
        self.audit.log(
            "departments.create",
            actor=ctx.user,
            entity_type="department",
            entity_id=department.id,
            summary=f"Created department {department.name}",
            changes=snapshot(department, _DEPARTMENT_FIELDS),
        )
        self.db.commit()
        self.db.refresh(department)
        return department

    def update_department(
        self, ctx: AuthContext, department_id: uuid.UUID, data: DepartmentUpdate
    ) -> Department:
        department = self.get_department(department_id)
        changes = data.model_dump(exclude_unset=True)
        ensure_unique(
            self.db,
            Department,
            "code",
            changes.get("code"),
            exclude_id=department.id,
            label="department code",
        )
        ensure_unique(
            self.db,
            Department,
            "name",
            changes.get("name"),
            exclude_id=department.id,
            label="department name",
        )
        before = snapshot(department, _DEPARTMENT_FIELDS)
        apply_changes(department, changes, required=("code", "name", "is_active"))
        self._log("departments.update", ctx, department, "department", before, _DEPARTMENT_FIELDS)
        self.db.commit()
        self.db.refresh(department)
        return department

    def delete_department(self, ctx: AuthContext, department_id: uuid.UUID) -> None:
        department = self.get_department(department_id)
        name = department.name
        delete_or_block(self.db, department, "department")
        self.audit.log(
            "departments.delete",
            actor=ctx.user,
            entity_type="department",
            entity_id=department_id,
            summary=f"Deleted department {name}",
        )
        self.db.commit()

    # ------------------------------------------------------------------ helpers
    def _log(
        self,
        action: str,
        ctx: AuthContext,
        obj: Any,
        entity_type: str,
        before: dict[str, Any],
        fields: tuple[str, ...],
    ) -> None:
        delta = diff(before, snapshot(obj, fields))
        if delta:
            self.audit.log(
                action, actor=ctx.user, entity_type=entity_type, entity_id=obj.id, changes=delta
            )
