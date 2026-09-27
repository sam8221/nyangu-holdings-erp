# System Architecture

```text
Browser ──HTTPS──► nginx (frontend container)
                    ├─ /            React + Vite build (static files)
                    └─ /api/*  ───► FastAPI backend (uvicorn) ───► PostgreSQL
```

## Backend layers

| Layer | Folder | Responsibility |
| ----- | ------ | -------------- |
| Routers | `app/routers/` | HTTP only: parse and validate input, check permissions, call a service, wrap the result |
| Services | `app/services/` | Business rules, transactions, audit entries and notifications |
| Repositories | `app/repositories/` | Database queries and shared query helpers |
| Models | `app/models/` | SQLAlchemy tables and computed properties |
| Schemas | `app/schemas/` | Pydantic request and response shapes |

Cross-cutting pieces: JWT + RBAC dependencies (`app/auth/`), request ID, logging, security
headers, body size limit and rate limiting (`app/middleware/`), and a stock engine that every
module changing stock goes through (`app/services/inventory_service.py`).

Each request gets its own database session. A service commits once at the end, so a business
action and its audit entry, notifications and document number either all happen or none do.
