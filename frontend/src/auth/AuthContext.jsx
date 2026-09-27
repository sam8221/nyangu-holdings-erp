import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { setSessionExpiredHandler } from '../api/client'
import { authApi } from '../api/endpoints'
import { clearTokens, loadTokens, saveTokens } from '../api/tokens'
import { hasAll, hasAny } from './permissions'

const AuthContext = createContext(null)

const ANONYMOUS = { status: 'anonymous', user: null, expired: false }

export function AuthProvider({ children }) {
  const queryClient = useQueryClient()
  const [state, setState] = useState(() =>
    loadTokens() ? { status: 'loading', user: null, expired: false } : ANONYMOUS,
  )

  const reload = useCallback(async () => {
    try {
      const user = await authApi.me()
      setState({ status: 'authenticated', user, expired: false })
      return user
    } catch {
      clearTokens()
      setState(ANONYMOUS)
      return null
    }
  }, [])

  // Restore the session after a page reload.
  useEffect(() => {
    if (!loadTokens()) return undefined
    let cancelled = false
    authApi
      .me()
      .then((user) => {
        if (!cancelled) setState({ status: 'authenticated', user, expired: false })
      })
      .catch(() => {
        if (cancelled) return
        clearTokens()
        setState(ANONYMOUS)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Any request that finally fails with 401 ends the session.
  useEffect(() => {
    setSessionExpiredHandler(() => {
      queryClient.clear()
      setState({ status: 'anonymous', user: null, expired: true })
    })
  }, [queryClient])

  const login = useCallback(async (identifier, password) => {
    const data = await authApi.login(identifier, password)
    saveTokens(data)
    setState({ status: 'authenticated', user: data.user, expired: false })
    return data.user
  }, [])

  const logout = useCallback(
    async ({ allDevices = false } = {}) => {
      const tokens = loadTokens()
      try {
        if (tokens) {
          await authApi.logout({ refresh_token: tokens.refresh_token, all_devices: allDevices })
        }
      } catch {
        // The server may already consider the session over; sign out locally anyway.
      } finally {
        clearTokens()
        queryClient.clear()
        setState(ANONYMOUS)
      }
    },
    [queryClient],
  )

  const value = useMemo(
    () => ({
      ...state,
      login,
      logout,
      reload,
      can: (...perms) => hasAll(state.user, perms),
      canAny: (...perms) => hasAny(state.user, perms),
    }),
    [state, login, logout, reload],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
