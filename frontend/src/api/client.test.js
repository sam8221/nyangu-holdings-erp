import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, cleanParams, setSessionExpiredHandler } from './client'
import { applyFieldErrors, errorMessage } from './errors'
import { loadTokens, saveTokens } from './tokens'

function httpError(config, status, data = {}) {
  const error = new Error(`HTTP ${status}`)
  error.config = config
  error.response = { status, data, config, headers: {} }
  return error
}

describe('api client token handling', () => {
  let calls
  const originalAdapter = api.defaults.adapter

  beforeEach(() => {
    calls = []
    saveTokens({ access_token: 'old-access', refresh_token: 'old-refresh' })
  })

  afterEach(() => {
    api.defaults.adapter = originalAdapter
    setSessionExpiredHandler(() => {})
  })

  it('sends the bearer token', async () => {
    api.defaults.adapter = async (config) => {
      calls.push(config.headers.Authorization)
      return { data: { data: 'ok' }, status: 200, statusText: 'OK', headers: {}, config }
    }
    await api.get('/auth/me')
    expect(calls).toEqual(['Bearer old-access'])
  })

  it('refreshes once on 401 and retries the request', async () => {
    api.defaults.adapter = async (config) => {
      calls.push(`${config.url} ${config.headers.Authorization || ''}`.trim())
      if (config.url === '/auth/refresh') {
        return {
          data: { data: { access_token: 'new-access', refresh_token: 'new-refresh' } },
          status: 200,
          statusText: 'OK',
          headers: {},
          config,
        }
      }
      if (config.headers.Authorization === 'Bearer old-access') throw httpError(config, 401)
      return { data: { data: 'fresh' }, status: 200, statusText: 'OK', headers: {}, config }
    }
    const response = await api.get('/users')
    expect(response.data.data).toBe('fresh')
    expect(calls).toEqual(['/users Bearer old-access', '/auth/refresh', '/users Bearer new-access'])
    expect(loadTokens()).toEqual({ access_token: 'new-access', refresh_token: 'new-refresh' })
  })

  it('ends the session when the refresh fails', async () => {
    const expired = vi.fn()
    setSessionExpiredHandler(expired)
    api.defaults.adapter = async (config) => {
      throw httpError(config, 401, { message: 'Invalid refresh token' })
    }
    await expect(api.get('/users')).rejects.toThrow()
    expect(expired).toHaveBeenCalledTimes(1)
    expect(loadTokens()).toBeNull()
  })

  it('does not try to refresh for sign-in failures', async () => {
    const expired = vi.fn()
    setSessionExpiredHandler(expired)
    api.defaults.adapter = async (config) => {
      calls.push(config.url)
      throw httpError(config, 401, { message: 'Invalid email/username or password' })
    }
    await expect(api.post('/auth/login', {}, { skipAuth: true })).rejects.toThrow()
    expect(calls).toEqual(['/auth/login'])
    expect(expired).not.toHaveBeenCalled()
  })
})

describe('helpers', () => {
  it('drops empty params', () => {
    expect(cleanParams({ a: 1, b: '', c: null, d: undefined, e: 0, f: false })).toEqual({
      a: 1,
      e: 0,
      f: false,
    })
  })

  it('reads API error messages and field errors', () => {
    const error = {
      response: {
        data: {
          message: 'Validation failed',
          errors: [
            { field: 'email', message: 'Invalid email' },
            { field: 'lines.0.product_id', message: 'Not found' },
            { field: null, message: 'General' },
          ],
        },
      },
    }
    expect(errorMessage(error)).toBe('Validation failed')
    expect(errorMessage({ code: 'ERR_NETWORK' })).toBe('Cannot reach the server. Check your connection.')
    const form = { setFields: vi.fn() }
    expect(applyFieldErrors(form, error)).toBe(true)
    expect(form.setFields).toHaveBeenCalledWith([
      { name: ['email'], errors: ['Invalid email'] },
      { name: ['lines', 0, 'product_id'], errors: ['Not found'] },
    ])
  })
})
