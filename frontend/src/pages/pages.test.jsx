import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { authApi } from '../api/endpoints'
import { loadTokens } from '../api/tokens'
import DataTable from '../components/DataTable'
import { renderWithProviders } from '../test/render'
import Login from './auth/Login'

vi.mock('../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    authApi: { ...actual.authApi, login: vi.fn(), me: vi.fn() },
  }
})

const ADMIN = {
  id: 'u1',
  full_name: 'System Administrator',
  email: 'admin@nyangu.com',
  roles: [{ id: 'r1', name: 'SUPER_ADMIN', display_name: 'Super Administrator' }],
  permissions: [],
  is_super_admin: true,
}

describe('Login page', () => {
  beforeEach(() => vi.clearAllMocks())

  it('signs in and goes to the dashboard', async () => {
    authApi.login.mockResolvedValue({
      access_token: 'a',
      refresh_token: 'r',
      user: ADMIN,
    })
    renderWithProviders(
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/dashboard" element={<div>Dashboard reached</div>} />
      </Routes>,
      { route: '/login' },
    )
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Email or username'), 'admin@nyangu.com')
    await user.type(screen.getByLabelText('Password'), 'Secret!Pass1')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByText('Dashboard reached')).toBeInTheDocument()
    expect(authApi.login).toHaveBeenCalledWith('admin@nyangu.com', 'Secret!Pass1')
    expect(loadTokens()).toEqual({ access_token: 'a', refresh_token: 'r' })
  })

  it('shows the API error message', async () => {
    authApi.login.mockRejectedValue({
      response: { status: 401, data: { message: 'Invalid email/username or password' } },
    })
    renderWithProviders(<Login />, { route: '/login' })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Email or username'), 'nobody')
    await user.type(screen.getByLabelText('Password'), 'wrong')
    await user.click(screen.getByRole('button', { name: /sign in/i }))
    expect(await screen.findByText('Invalid email/username or password')).toBeInTheDocument()
  })

  it('requires both fields', async () => {
    renderWithProviders(<Login />, { route: '/login' })
    await userEvent.setup().click(screen.getByRole('button', { name: /sign in/i }))
    expect(await screen.findByText('Enter your email or username')).toBeInTheDocument()
    expect(authApi.login).not.toHaveBeenCalled()
  })
})

describe('DataTable', () => {
  it('fetches rows with paging, search and filters', async () => {
    const fetcher = vi.fn(async (params) => ({
      items: [{ id: '1', name: `Row for ${params.search || 'all'}` }],
      meta: { page: 1, page_size: 20, total: 1, pages: 1 },
    }))
    renderWithProviders(
      <DataTable
        queryKey={['test']}
        fetcher={fetcher}
        filters={{ status: 'ACTIVE' }}
        columns={[{ title: 'Name', dataIndex: 'name', key: 'name', sortField: 'name' }]}
      />,
    )
    expect(await screen.findByText('Row for all')).toBeInTheDocument()
    expect(fetcher).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, page_size: 20, status: 'ACTIVE' }),
    )
    const user = userEvent.setup()
    await user.type(screen.getByPlaceholderText('Search'), 'cement{Enter}')
    await waitFor(() => expect(screen.getByText('Row for cement')).toBeInTheDocument())
    expect(screen.getByText('1 record')).toBeInTheDocument()
  })
})
