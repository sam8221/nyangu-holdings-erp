import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Spin } from 'antd'
import { RequireAuth, RequirePermission } from '../auth/guards'
import AppLayout from '../layout/AppLayout'
import { MENU_PAGES } from '../layout/menu'
import ForgotPassword from '../pages/auth/ForgotPassword'
import Login from '../pages/auth/Login'
import ResetPassword from '../pages/auth/ResetPassword'
import ComingSoon from '../pages/common/ComingSoon'
import NotFound from '../pages/common/NotFound'

// Each screen is loaded on first visit, keeping the initial download small.
const named = (loader, name) => lazy(() => loader().then((m) => ({ default: m[name] })))

/** Screens that are built. Every other menu entry shows a "coming next" placeholder. */
const BUILT = {
  '/dashboard': lazy(() => import('../pages/dashboard/Dashboard')),
  '/users': lazy(() => import('../pages/users/UsersPage')),
  '/roles': lazy(() => import('../pages/roles/RolesPage')),
  '/company': lazy(() => import('../pages/company/CompanyPage')),
  '/settings': lazy(() => import('../pages/settings/SettingsPage')),
  '/employees': lazy(() => import('../pages/hr/EmployeesPage')),
  '/leave': lazy(() => import('../pages/hr/LeavePage')),
  '/customers': named(() => import('../pages/partners/PartnerPages'), 'CustomersPage'),
  '/suppliers': named(() => import('../pages/partners/PartnerPages'), 'SuppliersPage'),
  '/products': lazy(() => import('../pages/inventory/ProductsPage')),
  '/warehouses': lazy(() => import('../pages/inventory/WarehousesPage')),
  '/inventory/stock': lazy(() => import('../pages/inventory/StockPage')),
  '/inventory/movements': lazy(() => import('../pages/inventory/MovementsPage')),
  '/sales/quotations': lazy(() => import('../pages/sales/QuotationsPage')),
  '/sales/invoices': lazy(() => import('../pages/sales/InvoicesPage')),
  '/sales/payments': lazy(() => import('../pages/sales/PaymentsPage')),
}

const pageFallback = (
  <div style={{ padding: 48, textAlign: 'center' }}>
    <Spin />
  </div>
)

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        {MENU_PAGES.map((page) => {
          const Page = BUILT[page.key]
          return (
            <Route
              key={page.key}
              path={page.key}
              element={
                <RequirePermission perms={page.perms}>
                  <Suspense fallback={pageFallback}>
                    {Page ? <Page /> : <ComingSoon title={page.label} />}
                  </Suspense>
                </RequirePermission>
              }
            />
          )
        })}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
