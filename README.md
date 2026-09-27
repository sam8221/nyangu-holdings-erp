# Nyangu Holdings ERP

Web-based ERP for Nyangu Holdings (Zambia, ZMW).

## Stack
- Frontend: React + Vite
- Backend: Python + FastAPI
- Database: PostgreSQL
- ORM: SQLAlchemy
- Authentication: JWT + RBAC

## Status
The backend is complete for every module below, with an automated test suite against PostgreSQL.
Setup, API, business rules and deployment are documented in [backend/README.md](backend/README.md),
and every endpoint is browsable in Swagger at `/docs` once the API is running.

The frontend is still a placeholder shell (login and dashboard pages only) and is the next piece
of work.

## Development order
| # | Area | Backend | Frontend |
| - | ---- | ------- | -------- |
| 1 | Project setup | Done | Shell only |
| 2 | Database | Done | — |
| 3 | Authentication and RBAC | Done | To do |
| 4 | Dashboard | Done | To do |
| 5 | Users | Done | To do |
| 6 | Employees | Done | To do |
| 7 | Customers and suppliers | Done | To do |
| 8 | Products and inventory | Done | To do |
| 9 | Sales | Done | To do |
| 10 | Procurement | Done | To do |
| 11 | Finance | Done | To do |
| 12 | Assets | Done | To do |
| 13 | Reports | Done | To do |
| 14 | Notifications and audit logs | Done | To do |
| 15 | Testing | Backend suite done | To do |
| 16 | Deployment | Docker, nginx and checklist done | — |

## Repository layout
- [backend/](backend/) — FastAPI application, migrations and tests
- [frontend/](frontend/) — React + Vite application
- [deployment/](deployment/) — Dockerfiles, docker-compose and nginx configuration
- [docs/](docs/) — project and technical documentation
