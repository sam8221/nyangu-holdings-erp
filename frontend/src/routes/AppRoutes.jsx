import { Navigate, Route, Routes } from 'react-router-dom'
import { RequireAuth, RequirePermission } from '../auth/guards'
import AppLayout from '../layout/AppLayout'
import { MENU_PAGES } from '../layout/menu'
import ForgotPassword from '../pages/auth/ForgotPassword'
import Login from '../pages/auth/Login'
import ResetPassword from '../pages/auth/ResetPassword'
import ComingSoon from '../pages/common/ComingSoon'
import NotFound from '../pages/common/NotFound'
import Dashboard from '../pages/dashboard/Dashboard'
import RolesPage from '../pages/roles/RolesPage'
import UsersPage from '../pages/users/UsersPage'

/** Screens that are built. Every other menu entry shows a "coming next" placeholder. */
const BUILT = {
  '/dashboard': Dashboard,
  '/users': UsersPage,
  '/roles': RolesPage,
}

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
                  {Page ? <Page /> : <ComingSoon title={page.label} />}
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
