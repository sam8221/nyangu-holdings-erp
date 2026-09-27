# Nyangu Holdings ERP — Frontend

React 19 + Vite + Ant Design 6, with a white and light-blue theme. Server data is handled by
TanStack Query; the API client renews expired access tokens automatically.

## Run it

The backend must be running on http://localhost:8000 (see `backend/README.md`).

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and sign in. In development, Vite proxies `/api` to the backend, so
there is no CORS setup to do. To point at another backend, set `VITE_PROXY_TARGET` before
`npm run dev`.

| Command | What it does |
| ------- | ------------ |
| `npm run dev` | Development server with hot reload |
| `npm run build` | Production build into `dist/` |
| `npm test` | Unit and component tests (Vitest + Testing Library) |
| `npm run lint` | ESLint, including the React hooks rules |

## What is built

- **Sign-in:** login with email or username, forgot password, reset password from the emailed
  link, change password, sign out (this device or all devices). Sessions renew silently; when a
  session truly ends the user is sent back to sign in with a short explanation.
- **Layout:** white sidebar and header with light-blue accents; the menu shows only the modules
  the user may use; notification bell with unread count and "mark all as read".
- **Dashboard:** figures for each module the user can view, pending approvals, six-month sales
  trend.
- **Users:** search, filter by status and role, sort, create, edit, change roles, activate or
  deactivate, reset password. Actions the API would refuse (for example managing a Super
  Administrator without being one) are not offered.
- **Roles:** list with user counts, create and edit with permissions grouped by module;
  permissions you do not hold cannot be granted.

Menu entries for the other modules open a "coming next" page until their screens are built.
Their APIs already work (see `/docs`).

## Structure

```text
src/
├── api/            # axios client (token refresh), endpoints, error helpers
├── auth/           # AuthContext, permission helpers, route guards
├── components/     # DataTable (server paging/sorting/search), PageHeader, StatusTag, charts
├── layout/         # App layout, sidebar menu definition, notifications, change password
├── pages/          # One folder per module
├── routes/         # Route table
├── utils/          # Formatting (money, dates), password rules
├── theme.js        # Colours and Ant Design theme tokens
└── main.jsx        # Providers: React Query, Ant Design, router, auth
```

## Conventions

- Money and quantities arrive as decimal strings; format them with `utils/format.js` and never
  do arithmetic on the formatted text.
- Use `useAuth().can(...)` / `canAny(...)` to show or hide actions. The backend still checks every
  request; hiding a button is only a convenience.
- New list pages should use `components/DataTable.jsx`: give it a `fetcher`, `columns` (add
  `sortField` to sortable columns, matching the API's sort fields) and optional `filters`.
- Show API field errors on forms with `applyFieldErrors(form, error)`.
