// Tokens are kept in localStorage so a session survives page reloads.
// The access token is short-lived (60 min) and refresh tokens are rotated on every use.
const KEY = 'nyangu-erp.auth'

export function loadTokens() {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function saveTokens({ access_token, refresh_token }) {
  localStorage.setItem(KEY, JSON.stringify({ access_token, refresh_token }))
}

export function clearTokens() {
  localStorage.removeItem(KEY)
}
