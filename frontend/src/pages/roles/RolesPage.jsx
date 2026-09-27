import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, App, Button, Card, Input, Space, Table, Tag, Typography } from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import { rolesApi } from '../../api/endpoints'
import { errorMessage } from '../../api/errors'
import { useAuth } from '../../auth/AuthContext'
import PageHeader from '../../components/PageHeader'
import RoleFormDrawer from './RoleFormDrawer'

export default function RolesPage() {
  const { can } = useAuth()
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [drawer, setDrawer] = useState({ open: false, role: null })

  const roles = useQuery({
    queryKey: ['roles', search],
    queryFn: () => rolesApi.list({ search: search || undefined }),
  })

  const remove = useMutation({
    mutationFn: (role) => rolesApi.remove(role.id),
    onSuccess: () => {
      message.success('Role deleted')
      queryClient.invalidateQueries({ queryKey: ['roles'] })
    },
    onError: (error) => message.error(errorMessage(error)),
  })

  const confirmDelete = (role) =>
    modal.confirm({
      title: `Delete ${role.display_name}?`,
      content: 'This cannot be undone.',
      okText: 'Delete',
      okButtonProps: { danger: true },
      onOk: () => remove.mutateAsync(role),
    })

  const columns = [
    {
      title: 'Role',
      key: 'name',
      render: (_, r) => (
        <div>
          <Typography.Text strong>{r.display_name}</Typography.Text>
          <div className="muted" style={{ fontSize: 12 }}>
            {r.name}
          </div>
        </div>
      ),
    },
    { title: 'Description', dataIndex: 'description', key: 'description', render: (v) => v || '—' },
    {
      title: 'Type',
      key: 'type',
      render: (_, r) => (r.is_system ? <Tag color="geekblue">System</Tag> : <Tag>Custom</Tag>),
    },
    {
      title: 'Status',
      key: 'status',
      render: (_, r) => (r.is_active ? <Tag color="green">Active</Tag> : <Tag>Inactive</Tag>),
    },
    { title: 'Users', dataIndex: 'user_count', key: 'user_count', align: 'right' },
    {
      title: 'Permissions',
      key: 'permissions',
      align: 'right',
      render: (_, r) => r.permissions.length,
    },
    {
      title: '',
      key: 'actions',
      width: 96,
      render: (_, r) => (
        <Space>
          {can('roles.update') && r.name !== 'SUPER_ADMIN' && (
            <Button
              type="text"
              icon={<EditOutlined />}
              aria-label={`Edit ${r.display_name}`}
              onClick={() => setDrawer({ open: true, role: r })}
            />
          )}
          {can('roles.delete') && !r.is_system && (
            <Button
              type="text"
              danger
              icon={<DeleteOutlined />}
              disabled={r.user_count > 0}
              title={r.user_count > 0 ? 'Remove it from every user first' : undefined}
              aria-label={`Delete ${r.display_name}`}
              onClick={() => confirmDelete(r)}
            />
          )}
        </Space>
      ),
    },
  ]

  return (
    <>
      <PageHeader
        title="Roles"
        subtitle="Groups of permissions. A user's access is the sum of their roles."
        actions={
          can('roles.create') && (
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setDrawer({ open: true, role: null })}
            >
              New role
            </Button>
          )
        }
      />
      <Card styles={{ body: { padding: 16 } }}>
        <div className="page-toolbar">
          <Input.Search
            allowClear
            placeholder="Search roles"
            style={{ width: 280 }}
            onSearch={(v) => setSearch(v.trim())}
          />
        </div>
        {roles.isError && (
          <Alert type="error" showIcon title={errorMessage(roles.error)} style={{ marginBottom: 12 }} />
        )}
        <Table
          rowKey="id"
          columns={columns}
          dataSource={roles.data || []}
          loading={roles.isFetching}
          pagination={false}
          scroll={{ x: 'max-content' }}
        />
      </Card>
      <RoleFormDrawer
        open={drawer.open}
        role={drawer.role}
        onClose={() => setDrawer({ open: false, role: null })}
      />
    </>
  )
}
