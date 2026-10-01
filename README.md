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

The frontend (React + Ant Design, white and light-blue theme) has its foundation in place:
sign-in and password flows, the permission-aware layout, the dashboard, users and roles, company
setup, HR, customers, suppliers, products, inventory and sales (quotations in the company's
own layout with the logo, invoices and payments). See [frontend/README.md](frontend/README.md).
Procurement, finance, assets and reports are next.

## Development order
| # | Area | Backend | Frontend |
| - | ---- | ------- | -------- |
| 1 | Project setup | Done | Done |
| 2 | Database | Done | — |
| 3 | Authentication and RBAC | Done | Done |
| 4 | Dashboard | Done | Done |
| 5 | Users | Done | Done (users and roles) |
| 6 | Employees | Done | Done (employees and leave) |
| 7 | Customers and suppliers | Done | Done |
| 8 | Products and inventory | Done | Done |
| 9 | Sales | Done (incl. quotations) | Done (quotations, invoices, payments) |
| 10 | Procurement | Done | To do |
| 11 | Finance | Done | To do |
| 12 | Assets | Done | To do |
| 13 | Reports | Done | To do |
| 14 | Notifications and audit logs | Done | To do |
| 15 | Testing | Backend suite done | Foundation tests done |
| 16 | Deployment | Docker, nginx and checklist done | — |

## Repository layout
- [backend/](backend/) — FastAPI application, migrations and tests
- [frontend/](frontend/) — React + Vite application
- [deployment/](deployment/) — Dockerfiles, docker-compose and nginx configuration
- [docs/](docs/) — project and technical documentation
