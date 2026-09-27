# API Documentation

The API is self-documenting. With the backend running:

- Swagger UI (interactive): http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/api/v1/openapi.json

A module-by-module overview of endpoints, permissions, the response envelope, error codes,
pagination and document numbers is in [backend/README.md](../../backend/README.md#api-overview).

## Conventions

- Base path: `/api/v1`
- Authentication: `Authorization: Bearer <access_token>` from `POST /auth/login`
- Every response: `{ "success": ..., "message": ..., "data": ... }` or an error envelope with
  `error_code` and field-level `errors`
- Money and quantities are decimal strings (`"1500.00"`)
- Lists accept `page`, `page_size` (max 100), `search`, `sort_by`, `sort_order`
- Each response carries `X-Request-ID`; quote it when reporting a problem
