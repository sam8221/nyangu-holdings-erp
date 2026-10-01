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
- **Company:** profile (TPIN, VAT, financial year), branches (one head office) and departments;
  **Settings:** default VAT, payment terms, leave entitlement, low-stock alerts, invoice footer.
- **HR:** employees (salary and bank details only for users allowed to see them), termination,
  leave balances; leave requests with working-day count, balance check, approve/reject/cancel.
- **Customers and suppliers:** credit limits, payment terms, TPIN, contacts, bank details.
- **Products:** goods and services, categories, prices, VAT rate, reorder level, stock per
  warehouse.
- **Inventory:** warehouses, stock levels, low-stock list, adjustments (signed change or physical
  count), transfers between warehouses, and the movement ledger.
- **Sales:** quotations (numbered automatically, sent/accepted/declined, PDF in the company
  layout with the logo, convert to invoice), invoices (draft, approve and issue, cancel, PDF,
  record payments, details with payment history) and the payments list with voiding. One shared
  form handles both documents: picking a product fills in its price and VAT rate, and totals
  update as you type, with or without VAT included in the prices.
- **Automatic numbers:** quotations, customers, suppliers and (when left blank) product item
  codes are numbered by the server; invoices are numbered when issued.

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
- Simple reference data (list + create/edit modal + delete) can use `components/CrudPage.jsx`;
  pick related records with `components/RemoteSelect.jsx`, which searches the API as you type.
- Never send fields a user cannot see (for example salary without `employees.view_salary`):
  the API returns them blank, and sending the blank back would erase the stored value.
- Show API field errors on forms with `applyFieldErrors(form, error)`.
