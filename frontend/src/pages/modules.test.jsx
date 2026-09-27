import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import dayjs from 'dayjs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Form, Input } from 'antd'
import { authApi, employeesApi } from '../api/endpoints'
import { saveTokens } from '../api/tokens'
import CrudPage from '../components/CrudPage'
import { renderWithProviders } from '../test/render'
import EmployeeFormDrawer from './hr/EmployeeFormDrawer'
import { workingDays } from './hr/LeavePage'

const emptyPage = { items: [], meta: { page: 1, page_size: 50, total: 0, pages: 0 } }

vi.mock('../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal()
  const empty = vi.fn(async () => ({ items: [], meta: { page: 1, page_size: 50, total: 0, pages: 0 } }))
  return {
    ...actual,
    authApi: { ...actual.authApi, me: vi.fn() },
    employeesApi: { ...actual.employeesApi, list: empty, update: vi.fn(), create: vi.fn() },
    departmentsApi: { ...actual.departmentsApi, list: empty },
    branchesApi: { ...actual.branchesApi, list: empty },
    usersApi: { ...actual.usersApi, list: empty },
  }
})

function signInAs(user) {
  saveTokens({ access_token: 'a', refresh_token: 'r' })
  authApi.me.mockResolvedValue(user)
}

const user = (permissions) => ({
  id: 'me',
  full_name: 'Test User',
  email: 't@x.com',
  roles: [],
  permissions,
  is_super_admin: false,
})

describe('workingDays', () => {
  it('counts Monday to Friday only', () => {
    const monday = dayjs('2026-10-05')
    expect(workingDays(monday, monday.add(4, 'day'))).toBe(5)
    expect(workingDays(monday, monday.add(6, 'day'))).toBe(5)
    expect(workingDays(monday.add(5, 'day'), monday.add(6, 'day'))).toBe(0)
    expect(workingDays(monday.add(1, 'day'), monday)).toBe(0)
  })
})

function NameField() {
  return (
    <Form.Item name="name" label="Name" rules={[{ required: true }]}>
      <Input />
    </Form.Item>
  )
}

describe('CrudPage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists records and creates a new one through the API', async () => {
    signInAs(user(['things.create', 'things.update']))
    const api = {
      list: vi.fn(async () => ({
        items: [{ id: '1', name: 'Existing thing' }],
        meta: { page: 1, page_size: 20, total: 1, pages: 1 },
      })),
      create: vi.fn(async (body) => ({ id: '2', ...body })),
      update: vi.fn(),
      remove: vi.fn(),
    }
    renderWithProviders(
      <CrudPage
        title="Things"
        entityLabel="Thing"
        queryKey={['things']}
        api={api}
        perms={{ create: 'things.create', update: 'things.update', delete: 'things.delete' }}
        FormFields={NameField}
        toPayload={(v) => ({ ...v, extra: true })}
        columns={[{ title: 'Name', dataIndex: 'name', key: 'name' }]}
      />,
    )
    expect(await screen.findByText('Existing thing')).toBeInTheDocument()

    const u = userEvent.setup()
    await u.click(screen.getByRole('button', { name: /new thing/i }))
    const dialog = await screen.findByRole('dialog')
    await u.type(within(dialog).getByLabelText('Name'), 'Brand new')
    await u.click(within(dialog).getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(api.create).toHaveBeenCalledWith({ name: 'Brand new', extra: true }))
  })

  it('hides actions the user may not perform', async () => {
    signInAs(user([]))
    const api = { list: vi.fn(async () => emptyPage), create: vi.fn(), update: vi.fn(), remove: vi.fn() }
    renderWithProviders(
      <CrudPage
        title="Things"
        entityLabel="Thing"
        queryKey={['things-ro']}
        api={api}
        perms={{ create: 'things.create' }}
        FormFields={NameField}
        columns={[{ title: 'Name', dataIndex: 'name', key: 'name' }]}
      />,
    )
    await screen.findByText('Things')
    expect(screen.queryByRole('button', { name: /new thing/i })).not.toBeInTheDocument()
  })
})

describe('EmployeeFormDrawer', () => {
  const employee = {
    id: 'e1',
    employee_number: 'EMP-00001',
    first_name: 'Chipo',
    middle_name: null,
    last_name: 'Mulenga',
    full_name: 'Chipo Mulenga',
    gender: null,
    date_of_birth: null,
    national_id: null,
    napsa_number: null,
    tpin: null,
    email: null,
    phone: null,
    address: null,
    branch: null,
    department: null,
    manager_id: null,
    user_id: null,
    job_title: 'Clerk',
    employment_type: 'PERMANENT',
    status: 'ACTIVE',
    hire_date: '2024-01-15',
    basic_salary: null, // hidden by the API for this user
    bank_name: null,
    bank_account_number: null,
    emergency_contact_name: null,
    emergency_contact_phone: null,
  }

  it('never sends salary fields for users who cannot see them', async () => {
    signInAs(user(['employees.view', 'employees.update']))
    employeesApi.update.mockResolvedValue({ ...employee, job_title: 'Senior clerk' })
    renderWithProviders(<EmployeeFormDrawer open employee={employee} onClose={() => {}} />)

    const title = await screen.findByLabelText(/^Job title/)
    const u = userEvent.setup()
    await u.clear(title)
    await u.type(title, 'Senior clerk')
    await u.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(employeesApi.update).toHaveBeenCalled())
    const [id, body] = employeesApi.update.mock.calls[0]
    expect(id).toBe('e1')
    expect(body.job_title).toBe('Senior clerk')
    expect(body.hire_date).toBe('2024-01-15')
    expect(body).not.toHaveProperty('basic_salary')
    expect(body).not.toHaveProperty('bank_account_number')
    expect(body).not.toHaveProperty('user_id')
    expect(screen.getByText(/Salary and bank details are hidden/)).toBeInTheDocument()
  })
})
