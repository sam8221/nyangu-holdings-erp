# Database Documentation

PostgreSQL, managed only through Alembic migrations in `backend/migrations/versions/`.
Models live in `backend/app/models/`, one file per module.

## Conventions

- UUID primary keys; timezone-aware `created_at` / `updated_at` (stored in UTC)
- Money `NUMERIC(14,2)`, quantities `NUMERIC(14,3)`, rates `NUMERIC(5,2)`
- Status columns are strings guarded by `CHECK` constraints
- Constraint names are deterministic: `pk_`, `fk_`, `uq_`, `ix_`, `ck_`
- Foreign keys to reference data use `RESTRICT`, so records in use cannot be deleted

## Tables by module

| Module | Tables | Migration |
| ------ | ------ | --------- |
| Users and RBAC | `users`, `roles`, `permissions`, `user_roles`, `role_permissions`, `refresh_tokens`, `revoked_access_tokens` | 0001 |
| Platform | `audit_logs`, `notifications`, `password_reset_tokens`, `document_sequences` | 0002 |
| Company and HR | `company`, `branches`, `departments`, `system_settings`, `employees`, `leave_requests` | 0003 |
| Master data | `customers`, `suppliers`, `product_categories`, `products` | 0004 |
| Inventory | `warehouses`, `stock_levels`, `stock_movements` | 0005 |
| Sales | `sales_invoices`, `sales_invoice_lines`, `customer_payments` | 0006 |
| Procurement | `purchase_orders`, `purchase_order_lines`, `goods_receipts`, `goods_receipt_lines` | 0007 |
| Finance | `expense_categories`, `expenses`, `supplier_bills`, `supplier_payments` | 0008 |
| Assets | `asset_categories`, `assets` | 0009 |

## Key invariants

- `stock_levels.quantity >= 0`; every change has a matching `stock_movements` row with
  `balance_after`
- `sales_invoices.amount_paid` and `supplier_bills.amount_paid` stay between 0 and `total`
- Voided payments keep their row (`status = 'VOIDED'`) for the audit trail
- `document_sequences` holds one counter per prefix and year (e.g. `INV-2026`)
