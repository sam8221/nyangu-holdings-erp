import axios from 'axios'
import { clearTokens, loadTokens, saveTokens } from './tokens'

export const API_BASE = import.meta.env.VITE_API_URL || '/api/v1'

export const api = axios.create({ baseURL: API_BASE, timeout: 30_000 })

let sessionExpiredHandler = () => {}
let refreshPromise = null

/** Called once the session cannot be renewed (e.g. refresh token expired or revoked). */
export function setSessionExpiredHandler(handler) {
  sessionExpiredHandler = handler
}

/** Exchange the refresh token for a new pair. Concurrent callers share one request. */
export function refreshTokens() {
  if (!refreshPromise) {
    const refreshToken = loadTokens()?.refresh_token
    refreshPromise = api
      .post('/auth/refresh', { refresh_token: refreshToken }, { skipAuth: true })
      .then((res) => {
        saveTokens(res.data.data)
        return res.data.data
      })
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

api.interceptors.request.use((config) => {
  const tokens = loadTokens()
  if (tokens?.access_token && !config.skipAuth) {
    config.headers.Authorization = `Bearer ${tokens.access_token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const { config, response } = error
    const canRetry =
      response?.status === 401 &&
      config &&
      !config.skipAuth &&
      !config._retried &&
      loadTokens()?.refresh_token
    if (!canRetry) {
      if (response?.status === 401 && config && !config.skipAuth) {
        clearTokens()
        sessionExpiredHandler()
      }
      throw error
    }
    config._retried = true
    try {
      await refreshTokens()
    } catch {
      clearTokens()
      sessionExpiredHandler()
      throw error
    }
    return api(config)
  },
)

/** The API wraps everything in { success, message, data }; most callers only want data. */
export const unwrap = (response) => response.data.data

/** Drop empty values so they are not sent as filters. */
export function cleanParams(params) {
  return Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''),
  )
}
