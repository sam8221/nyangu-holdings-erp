import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Dropdown, Select, Space, Tag, Typography } from 'antd'
import { MoreOutlined, PlusOutlined } from '@ant-design/icons'
import { rolesApi, usersApi } from '../../api/endpoints'
import { errorMessage } from '../../api/errors'
import { useAuth } from '../../auth/AuthContext'
import DataTable from '../../components/DataTable'
import PageHeader from '../../components/PageHeader'
import StatusTag from '../../components/StatusTag'
import { formatDateTime } from '../../utils/format'
import ResetPasswordModal from './ResetPasswordModal'
import UserFormModal from './UserFormModal'
import UserRolesModal from './UserRolesModal'

const isSuperAdmin = (user) => user.roles.some((r) => r.name === 'SUPER_ADMIN')

export default function UsersPage() {
  const { user: me, can } = useAuth()
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const [filters, setFilters] = useState({ status: undefined, role: undefined })
  const [dialog, setDialog] = useState({ type: null, user: null })
  const close = () => setDialog({ type: null, user: null })

  const roles = useQuery({ queryKey: ['roles'], queryFn: () => rolesApi.list(), enabled: can('roles.view') })

  const statusMutation = useMutation({
    mutationFn: ({ user, status }) => usersApi.setStatus(user.id, status),
    onSuccess: (saved) => {
      message.success(`${saved.full_name} is now ${saved.status.toLowerCase()}`)
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
    onError: (error) => message.error(errorMessage(error)),
  })

  const confirmStatus = (user) => {
    const deactivate = user.status === 'ACTIVE'
    modal.confirm({
      title: deactivate ? `Deactivate ${user.full_name}?` : `Reactivate ${user.full_name}?`,
      content: deactivate
        ? 'They will be signed out immediately and will not be able to sign in.'
        : 'They will be able to sign in again.',
      okText: deactivate ? 'Deactivate' : 'Reactivate',
      okButtonProps: { danger: deactivate },
      onOk: () => statusMutation.mutateAsync({ user, status: deactivate ? 'INACTIVE' : 'ACTIVE' }),
    })
  }

  const actionsFor = (user) => {
    const self = user.id === me.id
    // Only a Super Administrator may manage another Super Administrator (the API enforces this).
    const protectedTarget = isSuperAdmin(user) && !me.is_super_admin
    const items = []
    if (can('users.update') && !protectedTarget) items.push({ key: 'edit', label: 'Edit details' })
    if (can('users.assign_roles') && !self && !protectedTarget) {
      items.push({ key: 'roles', label: 'Change roles' })
    }
    if (can('users.reset_password') && !self && !protectedTarget) {
      items.push({ key: 'reset', label: 'Reset password' })
    }
    if (can('users.update') && !self && !protectedTarget) {
      items.push({ type: 'divider' })
      items.push({
        key: 'status',
        label: user.status === 'ACTIVE' ? 'Deactivate' : 'Reactivate',
        danger: user.status === 'ACTIVE',
      })
    }
    return items
  }

  const onAction = (key, user) => {
    if (key === 'status') confirmStatus(user)
    else setDialog({ type: key, user })
  }

  const columns = [
    {
      title: 'Name',
      key: 'full_name',
      sortField: 'full_name',
      render: (_, u) => (
        <div>
          <Typography.Text strong>{u.full_name}</Typography.Text>
          {u.id === me.id && (
            <Tag color="blue" style={{ marginInlineStart: 8 }}>
              You
            </Tag>
          )}
          <div className="muted" style={{ fontSize: 12 }}>
            @{u.username}
          </div>
        </div>
      ),
    },
    { title: 'Email', dataIndex: 'email', key: 'email', sortField: 'email' },
    { title: 'Phone', dataIndex: 'phone', key: 'phone', render: (v) => v || '—' },
    {
      title: 'Roles',
      key: 'roles',
      render: (_, u) =>
        u.roles.length ? (
          <Space size={[4, 4]} wrap>
            {u.roles.map((r) => (
              <Tag key={r.id} color={r.name === 'SUPER_ADMIN' ? 'geekblue' : 'blue'}>
                {r.display_name}
              </Tag>
            ))}
          </Space>
        ) : (
          <span className="muted">No roles</span>
        ),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      sortField: 'status',
      render: (s) => <StatusTag status={s} />,
    },
    {
      title: 'Last sign-in',
      dataIndex: 'last_login_at',
      key: 'last_login_at',
      sortField: 'last_login_at',
      render: formatDateTime,
    },
    {
      title: '',
      key: 'actions',
      fixed: 'right',
      width: 56,
      render: (_, u) => {
        const items = actionsFor(u)
        return items.length ? (
          <Dropdown
            trigger={['click']}
            menu={{ items, onClick: ({ key }) => onAction(key, u) }}
            placement="bottomRight"
          >
            <Button type="text" icon={<MoreOutlined />} aria-label={`Actions for ${u.full_name}`} />
          </Dropdown>
        ) : null
      },
    },
  ]

  const roleOptions = (roles.data || []).map((r) => ({ value: r.name, label: r.display_name }))

  return (
    <>
      <PageHeader
        title="Users"
        subtitle="People who can sign in, and what they can do."
        actions={
          can('users.create') && (
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setDialog({ type: 'create', user: null })}
            >
              New user
            </Button>
          )
        }
      />
      <DataTable
        queryKey={['users']}
        fetcher={usersApi.list}
        columns={columns}
        filters={filters}
        searchPlaceholder="Search name, email or username"
        toolbar={
          <>
            <Select
              allowClear
              placeholder="Any status"
              style={{ width: 150 }}
              value={filters.status}
              onChange={(status) => setFilters((f) => ({ ...f, status }))}
              options={[
                { value: 'ACTIVE', label: 'Active' },
                { value: 'INACTIVE', label: 'Inactive' },
              ]}
            />
            {can('roles.view') && (
              <Select
                allowClear
                placeholder="Any role"
                style={{ width: 200 }}
                value={filters.role}
                onChange={(role) => setFilters((f) => ({ ...f, role }))}
                options={roleOptions}
              />
            )}
          </>
        }
      />
      <UserFormModal
        open={dialog.type === 'create' || dialog.type === 'edit'}
        user={dialog.type === 'edit' ? dialog.user : null}
        roles={roles.data}
        onClose={close}
      />
      <UserRolesModal
        open={dialog.type === 'roles'}
        user={dialog.user}
        roles={roles.data}
        onClose={close}
      />
      <ResetPasswordModal open={dialog.type === 'reset'} user={dialog.user} onClose={close} />
    </>
  )
}
