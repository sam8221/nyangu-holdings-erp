"""Employees and leave."""

from __future__ import annotations

from datetime import date, timedelta

from app.services.hr_service import working_days
from app.utils.time import local_today
from tests.conftest import API, bearer, login


def monday(weeks_ahead: int = 2) -> date:
    today = local_today()
    return today + timedelta(days=(7 - today.weekday()) + 7 * (weeks_ahead - 1))


EMPLOYEE = {
    "first_name": "Chipo",
    "last_name": "Mulenga",
    "hire_date": "2023-03-01",
    "national_id": "123456/10/1",
    "email": "Chipo.Mulenga@NyanguHoldings.com",
    "job_title": "Accounts Clerk",
    "basic_salary": "8500.00",
    "bank_name": "Zanaco",
    "bank_account_number": "0123456789",
}


def _employee(client, headers, **overrides) -> dict:
    r = client.post(f"{API}/employees", json={**EMPLOYEE, **overrides}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def test_create_employee_generates_number(client, auth_headers) -> None:
    hr = auth_headers("HR_OFFICER")
    first = _employee(client, hr)
    second = _employee(client, hr, national_id=None, email=None, first_name="Bwalya")
    assert first["employee_number"] == "EMP-00001"
    assert second["employee_number"] == "EMP-00002"
    assert first["full_name"] == "Chipo Mulenga"
    assert first["email"] == "chipo.mulenga@nyanguholdings.com"
    assert first["basic_salary"] == "8500.00"


def test_salary_hidden_without_permission(client, auth_headers) -> None:
    emp = _employee(client, auth_headers("HR_OFFICER"))
    manager = auth_headers("MANAGER")  # employees.view but not view_salary
    r = client.get(f"{API}/employees/{emp['id']}", headers=manager)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["basic_salary"] is None and data["bank_account_number"] is None
    listed = client.get(f"{API}/employees", headers=manager).json()["data"]["items"][0]
    assert listed["basic_salary"] is None


def test_setting_salary_requires_permission(client, auth_headers) -> None:
    root = auth_headers("SUPER_ADMIN", username="root")
    client.post(
        f"{API}/roles",
        json={
            "name": "HR_CLERK",
            "display_name": "HR clerk",
            "permissions": ["employees.view", "employees.create", "employees.update"],
        },
        headers=root,
    )
    clerk = auth_headers("HR_CLERK")
    r = client.post(f"{API}/employees", json=EMPLOYEE, headers=clerk)
    assert r.status_code == 403
    without_salary = {
        k: v
        for k, v in EMPLOYEE.items()
        if k not in ("basic_salary", "bank_name", "bank_account_number")
    }
    assert client.post(f"{API}/employees", json=without_salary, headers=clerk).status_code == 201


def test_employee_validation_and_uniqueness(client, auth_headers) -> None:
    hr = auth_headers("HR_OFFICER")
    _employee(client, hr)
    dup = client.post(f"{API}/employees", json={**EMPLOYEE, "email": "other@x.com"}, headers=hr)
    assert dup.status_code == 409 and dup.json()["errors"][0]["field"] == "national_id"
    bad = client.post(
        f"{API}/employees",
        json={
            **EMPLOYEE,
            "national_id": None,
            "email": None,
            "basic_salary": "-5",
            "tpin": "abc",
            "date_of_birth": "2999-01-01",
        },
        headers=hr,
    )
    assert bad.status_code == 422
    fields = {e["field"] for e in bad.json()["errors"]}
    assert {"basic_salary", "tpin", "date_of_birth"} <= fields


def test_update_and_filter_employees(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    dept = client.post(
        f"{API}/departments", json={"code": "FIN", "name": "Finance"}, headers=admin
    ).json()["data"]
    emp = _employee(client, admin, department_id=dept["id"])
    upd = client.put(
        f"{API}/employees/{emp['id']}",
        json={"job_title": "Senior Accounts Clerk", "basic_salary": "9500.00"},
        headers=admin,
    )
    assert upd.status_code == 200
    assert upd.json()["data"]["job_title"] == "Senior Accounts Clerk"
    assert upd.json()["data"]["department"]["code"] == "FIN"
    filtered = client.get(
        f"{API}/employees", params={"department_id": dept["id"], "search": "chipo"}, headers=admin
    )
    assert filtered.json()["data"]["meta"]["total"] == 1
    # Salary changes are audited without the amounts.
    audit = client.get(
        f"{API}/audit-logs",
        params={"entity_id": emp["id"], "action": "employees.update"},
        headers=admin,
    ).json()["data"]["items"][0]
    assert audit["changes"]["basic_salary"] == {"from": "***", "to": "***"}
    assert "9500" not in str(audit)
    self_manager = client.put(
        f"{API}/employees/{emp['id']}", json={"manager_id": emp["id"]}, headers=admin
    )
    assert self_manager.status_code == 422


def test_terminate_employee_deactivates_linked_user(client, auth_headers, make_user) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    staff = make_user("SALES_OFFICER")
    session = login(client, staff.email)
    emp = _employee(client, admin, user_id=staff.id)

    r = client.post(
        f"{API}/employees/{emp['id']}/terminate",
        json={"termination_date": local_today().isoformat(), "reason": "End of contract"},
        headers=admin,
    )
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "TERMINATED"
    assert client.get(f"{API}/auth/me", headers=bearer(session["access_token"])).status_code == 401
    again = client.post(
        f"{API}/employees/{emp['id']}/terminate",
        json={"termination_date": local_today().isoformat(), "reason": "Twice"},
        headers=admin,
    )
    assert again.status_code == 422
    locked = client.put(f"{API}/employees/{emp['id']}", json={"job_title": "X"}, headers=admin)
    assert locked.status_code == 422


def test_user_can_only_be_linked_once(client, auth_headers, make_user) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    staff = make_user()
    _employee(client, admin, user_id=staff.id)
    dup = client.post(
        f"{API}/employees",
        json={**EMPLOYEE, "national_id": None, "email": None, "user_id": staff.id},
        headers=admin,
    )
    assert dup.status_code == 409


def test_working_days_skip_weekends() -> None:
    start = monday()
    assert working_days(start, start + timedelta(days=4)) == 5
    assert working_days(start, start + timedelta(days=6)) == 5
    assert working_days(start + timedelta(days=5), start + timedelta(days=6)) == 0


def test_leave_request_approval_flow(client, auth_headers, make_user) -> None:
    hr_user = make_user("HR_OFFICER")
    hr = bearer(login(client, hr_user.email)["access_token"])
    approver = make_user("MANAGER")
    approver_h = bearer(login(client, approver.email)["access_token"])
    emp = _employee(client, hr)
    start = monday()

    r = client.post(
        f"{API}/leave-requests",
        json={
            "employee_id": emp["id"],
            "leave_type": "ANNUAL",
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=4)).isoformat(),
            "reason": "Family visit",
        },
        headers=hr,
    )
    assert r.status_code == 201, r.text
    leave = r.json()["data"]
    assert leave["days"] == "5.0" and leave["status"] == "PENDING"
    assert leave["employee_number"] == emp["employee_number"]

    # The manager (leave.approve holder) was notified.
    notes = client.get(f"{API}/notifications", headers=approver_h).json()["data"]["items"]
    assert any(n["entity_id"] == leave["id"] and n["category"] == "APPROVAL" for n in notes)

    overlap = client.post(
        f"{API}/leave-requests",
        json={
            "employee_id": emp["id"],
            "leave_type": "SICK",
            "start_date": (start + timedelta(days=2)).isoformat(),
            "end_date": (start + timedelta(days=2)).isoformat(),
        },
        headers=hr,
    )
    assert overlap.status_code == 422

    approved = client.post(f"{API}/leave-requests/{leave['id']}/approve", headers=approver_h)
    assert approved.status_code == 200
    assert approved.json()["data"]["status"] == "APPROVED"
    assert approved.json()["data"]["reviewed_by_id"] == approver.id
    twice = client.post(f"{API}/leave-requests/{leave['id']}/approve", headers=approver_h)
    assert twice.status_code == 422

    balance = client.get(
        f"{API}/employees/{emp['id']}/leave-balance",
        params={"year": start.year},
        headers=hr,
    ).json()["data"]
    assert balance["taken"] == "5.0" and balance["remaining"] == "19.0"

    # The requester hears back.
    hr_notes = client.get(f"{API}/notifications", headers=hr).json()["data"]["items"]
    assert any("approved" in n["title"] for n in hr_notes)

    cancelled = client.post(f"{API}/leave-requests/{leave['id']}/cancel", headers=hr)
    assert cancelled.status_code == 200 and cancelled.json()["data"]["status"] == "CANCELLED"


def test_leave_rules(client, auth_headers, make_user) -> None:
    hr = auth_headers("HR_OFFICER")
    emp = _employee(client, hr)
    start = monday()
    weekend = client.post(
        f"{API}/leave-requests",
        json={
            "employee_id": emp["id"],
            "leave_type": "ANNUAL",
            "start_date": (start - timedelta(days=2)).isoformat(),
            "end_date": (start - timedelta(days=1)).isoformat(),
        },
        headers=hr,
    )
    assert weekend.status_code == 422 and "no working days" in weekend.json()["message"]

    too_long = client.post(
        f"{API}/leave-requests",
        json={
            "employee_id": emp["id"],
            "leave_type": "ANNUAL",
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=40)).isoformat(),
        },
        headers=hr,
    )
    assert too_long.status_code == 422 and "Not enough annual leave" in too_long.json()["message"]

    reversed_dates = client.post(
        f"{API}/leave-requests",
        json={
            "employee_id": emp["id"],
            "leave_type": "SICK",
            "start_date": start.isoformat(),
            "end_date": (start - timedelta(days=3)).isoformat(),
        },
        headers=hr,
    )
    assert reversed_dates.status_code == 422

    sick = client.post(
        f"{API}/leave-requests",
        json={
            "employee_id": emp["id"],
            "leave_type": "SICK",
            "start_date": start.isoformat(),
            "end_date": start.isoformat(),
        },
        headers=hr,
    ).json()["data"]
    no_comment = client.post(f"{API}/leave-requests/{sick['id']}/reject", json={}, headers=hr)
    assert no_comment.status_code == 422
    rejected = client.post(
        f"{API}/leave-requests/{sick['id']}/reject",
        json={"comment": "Please attach a medical note"},
        headers=hr,
    )
    assert rejected.json()["data"]["status"] == "REJECTED"
    listing = client.get(
        f"{API}/leave-requests", params={"status": "REJECTED", "employee_id": emp["id"]}, headers=hr
    )
    assert listing.json()["data"]["meta"]["total"] == 1


def test_cannot_approve_own_leave(client, make_user) -> None:
    hr_user = make_user("HR_OFFICER")
    headers = bearer(login(client, hr_user.email)["access_token"])
    emp = _employee(client, headers, user_id=hr_user.id)
    start = monday()
    leave = client.post(
        f"{API}/leave-requests",
        json={
            "employee_id": emp["id"],
            "leave_type": "ANNUAL",
            "start_date": start.isoformat(),
            "end_date": start.isoformat(),
        },
        headers=headers,
    ).json()["data"]
    r = client.post(f"{API}/leave-requests/{leave['id']}/approve", headers=headers)
    assert r.status_code == 422 and "your own" in r.json()["message"]


def test_employee_with_history_cannot_be_deleted(client, auth_headers) -> None:
    admin = auth_headers("ADMIN", username="admin1")
    emp = _employee(client, admin)
    fresh = _employee(client, admin, national_id=None, email=None)
    start = monday()
    client.post(
        f"{API}/leave-requests",
        json={
            "employee_id": emp["id"],
            "leave_type": "SICK",
            "start_date": start.isoformat(),
            "end_date": start.isoformat(),
        },
        headers=admin,
    )
    assert client.delete(f"{API}/employees/{emp['id']}", headers=admin).status_code == 422
    assert client.delete(f"{API}/employees/{fresh['id']}", headers=admin).status_code == 200
