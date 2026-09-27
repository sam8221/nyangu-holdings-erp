import { Navigate, useLocation } from 'react-router-dom'
import { Spin } from 'antd'
import { useAuth } from './AuthContext'
import Forbidden from '../pages/common/Forbidden'

export function FullPageSpinner() {
  return (
    <div style={{ display: 'grid', placeItems: 'center', height: '100vh' }}>
      <Spin size="large" />
    </div>
  )
}

/** Only signed-in users; everyone else goes to the login page and comes back afterwards. */
export function RequireAuth({ children }) {
  const { status } = useAuth()
  const location = useLocation()
  if (status === 'loading') return <FullPageSpinner />
  if (status !== 'authenticated') {
    return <Navigate to="/login" replace state={{ from: location }} />
  }
  return children
}

/** Render children only if the user holds any of `perms`; otherwise a 403 page. */
export function RequirePermission({ perms, children }) {
  const { canAny } = useAuth()
  return canAny(...(perms || [])) ? children : <Forbidden />
}
