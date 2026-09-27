# Nyangu Holdings ERP — Backend

REST API backend for the Nyangu Holdings Enterprise Resource Planning system (Zambia · ZMW · Africa/Lusaka).
Built with **FastAPI**, **PostgreSQL**, **SQLAlchemy 2.x**, **Alembic** and **Pydantic v2**, designed to be consumed by a React frontend.

> **Current status: Phase 1 complete.** Covers configuration, database, migrations, users, roles, permissions,
> JWT authentication and RBAC. Business modules (HR, sales, inventory, procurement, finance, …) are added phase by phase.

---

## Table of contents

1. [Tech stack](#tech-stack)
2. [Project structure](#project-structure)
3. [Prerequisites](#prerequisites)
4. [Setup (first run)](#setup-first-run)
5. [Running the API](#running-the-api)
6. [API overview](#api-overview)
7. [Authentication flow](#authentication-flow)
8. [Roles and permissions (RBAC)](#roles-and-permissions-rbac)
9. [Response format](#response-format)
10. [Pagination, search and sorting](#pagination-search-and-sorting)
11. [Database migrations](#database-migrations)
12. [Testing](#testing)
13. [Security notes](#security-notes)
14. [Environment variables](#environment-variables)
15. [Production deployment](#production-deployment)
16. [Roadmap](#roadmap)

---

## Tech stack

| Concern            | Choice                                           |
| ------------------ | ------------------------------------------------ |
| Language           | Python 3.12+                                     |
| Web framework      | FastAPI                                          |
| Database           | PostgreSQL 14+ (developed on 17)                 |
| ORM                | SQLAlchemy 2.x (typed `Mapped[]` models)         |
| Migrations         | Alembic                                          |
| Validation         | Pydantic v2 + pydantic-settings                  |
| Driver             | psycopg 3                                        |
| Auth               | JWT (PyJWT, HS256) with access + refresh tokens  |
| Password hashing   | Argon2id (argon2-cffi)                           |
| Tests              | pytest + FastAPI TestClient against real Postgres |
| Lint / format      | ruff (config in `pyproject.toml`)                |

---

## Project structure

```text
backend/
├── app/
│   ├── main.py              # App factory: middleware, routers, exception handlers
│   ├── config.py            # Settings loaded from environment / .env
│   ├── database.py          # Engine, session factory, get_db dependency
│   ├── models/              # SQLAlchemy models (User, Role, Permission, tokens)
│   ├── schemas/             # Pydantic request/response schemas + response envelope
│   ├── repositories/        # Database queries (no business rules)
│   ├── services/            # Business logic and rules (auth, users, roles)
│   ├── routers/             # HTTP endpoints (thin: validate → call service → respond)
│   ├── auth/                # Hashing, JWT, auth/RBAC dependencies, permission catalogue
│   ├── middleware/          # Request ID + logging, security headers, rate limiting
│   ├── utils/               # Exceptions, logging, validators, time helpers
│   └── seed/                # Development seed script
├── migrations/              # Alembic environment + versioned migrations
├── tests/                   # pytest suite
├── .env.example             # Template for .env (committed)
├── .env                     # Your local secrets (NEVER committed)
├── alembic.ini
├── pyproject.toml           # ruff configuration
├── pytest.ini
└── requirements.txt
```

Request flow: **router → service → repository → database**. Routers never contain business rules;
repositories never decide who is allowed to do what.

---

## Prerequisites

- Python **3.12 or newer** — check with `python --version`
- PostgreSQL **14 or newer**, running locally on port 5432
- Git
- (Recommended) VS Code with the Python extension

---

## Setup (first run)

### 1. Create the databases

Open `psql` (or pgAdmin) as the `postgres` user and run:

```sql
CREATE DATABASE nyangu_erp;
CREATE DATABASE nyangu_erp_test;   -- used only by the automated tests
```

### 2. Create a virtual environment and install dependencies

**Windows (PowerShell)**

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> If PowerShell blocks the activate script, run once:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

**macOS / Linux**

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

In VS Code: `Ctrl+Shift+P` → **Python: Select Interpreter** → choose the one inside `.venv`.

### 3. Configure environment variables

Copy the template and edit it:

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

In `.env`, set at minimum:

| Variable              | What to put                                                                 |
| --------------------- | --------------------------------------------------------------------------- |
| `DATABASE_URL`        | Replace `PASSWORD` with your Postgres password                              |
| `TEST_DATABASE_URL`   | Same, pointing at `nyangu_erp_test`                                         |
| `SECRET_KEY`          | A random value — generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `SEED_ADMIN_EMAIL`    | Email for the first administrator                                           |
| `SEED_ADMIN_PASSWORD` | Their initial password (or leave empty to be prompted)                      |

> ⚠️ `.env` is listed in `.gitignore`. Never commit it.

### 4. Create the tables

```bash
alembic upgrade head
```

### 5. Seed roles, permissions and the first admin

```bash
python -m app.seed.run
```

This creates the 60-permission catalogue, the 8 system roles with default grants, and one
`SUPER_ADMIN` account from `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD`. It is safe to run again:
existing data is left in place.

The admin password must be at least 10 characters with an uppercase letter, a lowercase letter,
a digit and a symbol.

---

## Running the API

Development (auto-reload):

```bash
uvicorn app.main:app --reload
```

Production-style:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then open:

| URL                                   | Purpose                           |
| ------------------------------------- | --------------------------------- |
| http://localhost:8000/docs            | Swagger UI (interactive)          |
| http://localhost:8000/redoc           | ReDoc documentation               |
| http://localhost:8000/api/v1/health   | Health check (API + database)     |

**Trying it in Swagger:** call `POST /api/v1/auth/login`, copy `access_token` from the response,
click **Authorize** (top right), paste the token, and every protected endpoint will work.

---

## API overview

All endpoints are versioned under `/api/v1`.

### Health

| Method | Path       | Auth | Description                                   |
| ------ | ---------- | ---- | --------------------------------------------- |
| GET    | `/health`  | No   | API + PostgreSQL status (503 if DB is down)   |

### Authentication

| Method | Path                     | Auth | Description                                          |
| ------ | ------------------------ | ---- | ---------------------------------------------------- |
| POST   | `/auth/login`            | No   | Log in with email **or** username; returns tokens + user |
| POST   | `/auth/refresh`          | No*  | Exchange a refresh token for a new pair (rotated)    |
| POST   | `/auth/logout`           | Yes  | Revoke current tokens; `all_devices: true` logs out everywhere |
| GET    | `/auth/me`               | Yes  | Current user, roles and effective permissions        |
| POST   | `/auth/change-password`  | Yes  | Change own password; returns a fresh token pair      |

\* Requires a valid refresh token in the body instead of an access token.

### Users

| Method | Path                            | Permission            | Description                         |
| ------ | ------------------------------- | --------------------- | ----------------------------------- |
| GET    | `/users`                        | `users.view`          | Paginated list, search, filter, sort |
| POST   | `/users`                        | `users.create`        | Create user (+ `users.assign_roles` to set roles) |
| GET    | `/users/{id}`                   | `users.view`          | User detail with permissions        |
| PUT    | `/users/{id}`                   | `users.update`        | Update profile fields               |
| PATCH  | `/users/{id}/status`            | `users.update`        | Activate / deactivate               |
| PUT    | `/users/{id}/roles`             | `users.assign_roles`  | Replace the user's roles            |
| POST   | `/users/{id}/reset-password`    | `users.reset_password`| Admin password reset                |

### Roles and permissions

| Method | Path              | Permission          | Description                                 |
| ------ | ----------------- | ------------------- | ------------------------------------------- |
| GET    | `/roles`          | `roles.view`        | List roles with permissions and user counts |
| POST   | `/roles`          | `roles.create`      | Create a custom role                        |
| GET    | `/roles/{id}`     | `roles.view`        | Role detail                                 |
| PUT    | `/roles/{id}`     | `roles.update`      | Update a role / replace its permissions     |
| DELETE | `/roles/{id}`     | `roles.delete`      | Delete an unused custom role                |
| GET    | `/permissions`    | `permissions.view`  | Full permission catalogue (`?module=users`) |

---

## Authentication flow

```text
POST /auth/login ──► access_token (60 min) + refresh_token (7 days)
        │
        ▼
Authorization: Bearer <access_token>  on every request
        │
   access token expired (401)?
        │
        ▼
POST /auth/refresh {refresh_token} ──► NEW access + NEW refresh token
                                       (old refresh token is now dead)
```

Example login request:

```json
POST /api/v1/auth/login
{ "identifier": "admin@nyanguholdings.com", "password": "********" }
```

Example response (abbreviated):

```json
{
  "success": true,
  "message": "Login successful",
  "data": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "token_type": "bearer",
    "expires_in": 3600,
    "refresh_expires_in": 604800,
    "user": {
      "id": "f236b9b7-...",
      "full_name": "System Administrator",
      "email": "admin@nyanguholdings.com",
      "roles": [{ "name": "SUPER_ADMIN", "display_name": "Super Administrator" }],
      "permissions": ["users.view", "users.create", "..."]
    }
  }
}
```

**How sessions are invalidated**

| Event                               | Effect                                                   |
| ----------------------------------- | -------------------------------------------------------- |
| Logout                              | Access token deny-listed; supplied refresh token revoked |
| Logout with `all_devices: true`     | Every token of that user stops working                   |
| Password change / admin reset       | All other sessions end immediately                       |
| User deactivated                    | All tokens stop working on the next request              |
| Old refresh token re-used           | Treated as theft — all of that user's sessions revoked   |

Each user has a `token_version` stored in the database and copied into every JWT. Bumping it
invalidates all existing tokens at once without keeping a list of them.

**Login protection:** after 5 consecutive wrong passwords the account is locked for 15 minutes,
and login is rate-limited to 10 attempts per minute per IP (both configurable).

---

## Roles and permissions (RBAC)

Permissions use the format `module.action` (for example `users.view`, `sales.approve`).
Roles are collections of permissions; users can hold several roles.

**System roles (seeded):**

| Role                  | Default access                                                  |
| --------------------- | --------------------------------------------------------------- |
| `SUPER_ADMIN`         | Everything; passes every permission check                       |
| `ADMIN`               | All permissions; cannot manage Super Administrators             |
| `MANAGER`             | View all business modules, approvals, reports, audit            |
| `ACCOUNTANT`          | Finance, plus read-only customers/suppliers/sales/procurement   |
| `HR_OFFICER`          | Employees (incl. salary), leave approval                        |
| `SALES_OFFICER`       | Customers and sales (no delete/approve)                         |
| `PROCUREMENT_OFFICER` | Suppliers and procurement (no approve)                          |
| `STOREKEEPER`         | Products and inventory                                          |

The full catalogue lives in [`app/auth/permissions.py`](app/auth/permissions.py) and is the single
source of truth. Permissions for later modules are already defined so roles can be configured now.

**Protecting an endpoint:**

```python
from app.auth.dependencies import AuthContext, require_permissions
from app.auth.permissions import Perm

@router.get("/users")
def list_users(ctx: Annotated[AuthContext, Depends(require_permissions(Perm.USERS_VIEW))]):
    ...
```

Permissions are loaded from the database on every request, so a role change takes effect
immediately — the user does not need to log in again.

**Built-in business rules**

- Only a `SUPER_ADMIN` can create, edit, deactivate or reset a Super Administrator, or grant that role.
- At least one active `SUPER_ADMIN` must always remain.
- Users cannot deactivate themselves or change their own roles.
- A non-super-admin can only grant permissions they already hold (prevents privilege escalation).
- The `SUPER_ADMIN` role cannot be edited; system roles cannot be deleted or deactivated.
- Roles still assigned to users cannot be deleted.
- Deactivated users cannot log in.

The frontend should use `GET /auth/me → permissions` to show or hide menus, **but the backend
enforces every check independently.** Hiding a button is never a security control.

---

## Response format

Every response uses the same envelope.

**Success**

```json
{ "success": true, "message": "User created successfully", "data": { } }
```

**Error**

```json
{
  "success": false,
  "message": "Validation failed",
  "error_code": "VALIDATION_ERROR",
  "errors": [
    { "field": "email", "message": "value is not a valid email address", "type": "value_error" }
  ]
}
```

| HTTP | `error_code`              | Meaning                                         |
| ---- | ------------------------- | ----------------------------------------------- |
| 400  | `BAD_REQUEST`             | e.g. wrong current password, invalid sort field |
| 401  | `UNAUTHENTICATED`         | Missing, invalid, expired or revoked token      |
| 403  | `FORBIDDEN`               | Logged in but lacking the permission            |
| 404  | `NOT_FOUND`               | Resource does not exist                         |
| 409  | `CONFLICT`                | Duplicate (e.g. email already used)             |
| 422  | `VALIDATION_ERROR`        | Request body/query failed validation            |
| 422  | `BUSINESS_RULE_VIOLATION` | Valid input that breaks a business rule         |
| 429  | `RATE_LIMITED`            | Too many requests                               |
| 500  | `INTERNAL_ERROR`          | Unexpected error (details logged, never shown)  |
| 503  | `DATABASE_ERROR`          | Database unavailable                            |

Stack traces, SQL, password hashes and secrets are never returned to clients.
Every response carries an `X-Request-ID` header to match it with the server logs.

---

## Pagination, search and sorting

List endpoints accept:

| Query param  | Default | Notes                                    |
| ------------ | ------- | ---------------------------------------- |
| `page`       | 1       | ≥ 1                                      |
| `page_size`  | 20      | 1–100 (requests above 100 are rejected)  |
| `search`     | —       | Case-insensitive text match              |
| `sort_by`    | varies  | Only whitelisted fields are accepted     |
| `sort_order` | varies  | `asc` or `desc`                          |

```text
GET /api/v1/users?page=1&page_size=20&search=banda&status=ACTIVE&role=ACCOUNTANT&sort_by=full_name&sort_order=asc
```

Paginated `data` looks like:

```json
{
  "items": [ ],
  "meta": { "page": 1, "page_size": 20, "total": 57, "pages": 3 }
}
```

---

## Database migrations

Never change tables by hand. Every schema change goes through Alembic:

```bash
# 1. Change or add models in app/models/ (and import new ones in app/models/__init__.py)
# 2. Generate a migration
alembic revision --autogenerate -m "create customers table"
# 3. REVIEW the generated file in migrations/versions/
# 4. Apply it
alembic upgrade head
```

Other useful commands:

```bash
alembic current          # which revision the DB is on
alembic history          # list migrations
alembic downgrade -1     # undo the last migration
alembic check            # fails if models and migrations are out of sync
```

Conventions: UUID primary keys everywhere, timezone-aware `created_at` / `updated_at` on every
major table, and deterministic constraint names (`pk_`, `fk_`, `uq_`, `ix_`, `ck_`) so migrations
stay stable. Timestamps are stored in UTC; convert to Africa/Lusaka for display.

---

## Testing

The tests run against a real PostgreSQL database (`TEST_DATABASE_URL`), built from the actual
Alembic migrations so the migrations are tested too. The test database is wiped before every
test, so **never point it at `nyangu_erp`** (the test setup refuses to).

```bash
pytest            # run everything
pytest -v         # verbose
pytest tests/test_auth.py -k refresh   # a subset
ruff check . && ruff format --check .  # lint and formatting
```

Current suite: **75 tests, all passing**, covering:

- **Authentication:** login by email/username, invalid login, Argon2 hashing, account lockout,
  rate limiting, expired/forged/`alg=none` tokens, refresh-token rotation and reuse detection,
  logout, logout-all-devices, password change
- **Users:** create, duplicates, validation, update, list/search/filter/sort, role assignment,
  deactivation, admin password reset
- **Permissions:** forbidden access by role, view-only users, Super Admin protection,
  privilege-escalation prevention, role changes applying without a new login, inactive roles
- **Roles:** custom role lifecycle, system-role protection, roles in use, permission catalogue,
  idempotent seeding
- **Platform:** health check (including database down), docs, security headers, request IDs, CORS,
  error envelope, safe 500s, configuration safety, log masking, every endpoint documented

---

## Security notes

- Passwords hashed with **Argon2id**; plain text is never stored or logged.
- Password policy: 10–128 characters, upper, lower, digit and symbol.
- JWT algorithm pinned to HS256 (blocks `alg=none` and algorithm-confusion attacks); issuer and
  token type are validated.
- Login timing is the same for existing and non-existing accounts, and wrong-email vs
  wrong-password return the same message.
- Security headers on every response (`nosniff`, `X-Frame-Options: DENY`, CSP, `no-store`;
  HSTS in production).
- CORS restricted to `CORS_ORIGINS`.
- Log messages are filtered to mask anything that looks like a password or token.
- SQL injection is prevented by SQLAlchemy parameter binding; sort fields are whitelisted.
- The app refuses to start in `staging`/`production` with a weak `SECRET_KEY` or with `DEBUG=true`.

**Known limitation:** the rate limiter is in-memory, which is correct for a single worker.
When running multiple workers or servers, move it to Redis (same interface in
`app/middleware/rate_limit.py`).

---

## Environment variables

| Variable                        | Default                  | Description                              |
| ------------------------------- | ------------------------ | ---------------------------------------- |
| `APP_NAME`                      | Nyangu Holdings ERP      | Shown in docs and health                 |
| `ENVIRONMENT`                   | development              | development / testing / staging / production |
| `DEBUG`                         | false                    | Must be false outside development        |
| `LOG_LEVEL`                     | INFO                     |                                          |
| `DATABASE_URL`                  | — (required)             | `postgresql+psycopg://user:pass@host:5432/nyangu_erp` |
| `TEST_DATABASE_URL`             | —                        | Disposable DB for pytest                 |
| `SECRET_KEY`                    | — (required)             | ≥ 32 random chars outside development    |
| `ACCESS_TOKEN_EXPIRE_MINUTES`   | 60                       |                                          |
| `REFRESH_TOKEN_EXPIRE_DAYS`     | 7                        |                                          |
| `MAX_FAILED_LOGIN_ATTEMPTS`     | 5                        | Before lockout                           |
| `ACCOUNT_LOCKOUT_MINUTES`       | 15                       |                                          |
| `LOGIN_RATE_LIMIT_PER_MINUTE`   | 10                       | Per IP                                   |
| `CORS_ORIGINS`                  | http://localhost:5173    | Comma-separated                          |
| `DEFAULT_CURRENCY`              | ZMW                      |                                          |
| `TIMEZONE`                      | Africa/Lusaka            |                                          |
| `SEED_ADMIN_EMAIL`              | —                        | First admin (seed only)                  |
| `SEED_ADMIN_PASSWORD`           | —                        | Leave empty to be prompted               |

---

## Production deployment

Checklist before going live:

- [ ] `ENVIRONMENT=production`, `DEBUG=false`, strong unique `SECRET_KEY`
- [ ] Managed PostgreSQL; the app connects as a dedicated user that **owns only its schema**
      (not the `postgres` superuser)
- [ ] `alembic upgrade head` run as part of each deployment
- [ ] Run behind a reverse proxy (Nginx/Caddy) that terminates **HTTPS**
- [ ] Start uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy IP>` so client IPs
      (used for rate limiting and logs) are correct
- [ ] `CORS_ORIGINS` set to the real frontend domain only
- [ ] Rate limiter moved to Redis if running more than one worker
- [ ] Logs shipped to a central system; error tracking (e.g. Sentry) configured
- [ ] Monitoring hits `/api/v1/health`
- [ ] Automated backups (see below)

**Backups.** Take automated daily `pg_dump` backups (or use the managed provider's point-in-time
recovery), keep them for an agreed retention period (e.g. 7 daily, 4 weekly, 12 monthly), store
them **outside this repository and off the application server**, and test a restore regularly.
Example:

```bash
pg_dump -Fc -h <host> -U <user> nyangu_erp > nyangu_erp_$(date +%F).dump
pg_restore -d nyangu_erp_restored nyangu_erp_2026-09-27.dump
```

Housekeeping: expired rows in `refresh_tokens` and `revoked_access_tokens` can be purged with
`TokenRepository.purge_expired()` (to be scheduled as a background job).

---

## Roadmap

| Phase | Scope                                             | Status        |
| ----- | ------------------------------------------------- | ------------- |
| 1     | Config, DB, Alembic, health, users, roles, permissions, JWT, RBAC | ✅ Done |
| 2     | Forgot/reset password by email, audit log foundation | Next        |
| 3     | Company, branches, employees                      | Planned       |
| 4     | Customers, suppliers, products                    | Planned       |
| 5     | Inventory, warehouses, stock movements            | Planned       |
| 6     | Sales, invoices, payments                         | Planned       |
| 7     | Procurement, purchase orders, goods received      | Planned       |
| 8     | Finance, expenses, receivables, payables          | Planned       |
| 9     | Assets, notifications, audit logs                 | Planned       |
| 10    | Dashboard, reports, production hardening          | Planned       |
