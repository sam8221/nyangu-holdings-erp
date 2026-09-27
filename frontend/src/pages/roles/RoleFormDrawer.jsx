import { useEffect, useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Col,
  Drawer,
  Form,
  Input,
  Row,
  Space,
  Spin,
  Switch,
  Tooltip,
} from 'antd'
import { permissionsApi, rolesApi } from '../../api/endpoints'
import { applyFieldErrors, errorMessage } from '../../api/errors'
import { useAuth } from '../../auth/AuthContext'
import { humanize } from '../../utils/format'

/** Create (role = null) or edit a role and its permissions, grouped by module. */
export default function RoleFormDrawer({ open, role, onClose }) {
  const [form] = Form.useForm()
  const { message } = App.useApp()
  const { user: me } = useAuth()
  const queryClient = useQueryClient()
  const editing = Boolean(role)
  const permissions = useQuery({ queryKey: ['permissions'], queryFn: permissionsApi.list, enabled: open })

  const modules = useMemo(() => {
    const groups = {}
    for (const p of permissions.data || []) {
      ;(groups[p.module] ||= []).push(p)
    }
    return Object.entries(groups)
  }, [permissions.data])

  useEffect(() => {
    if (!open) return
    form.resetFields()
    form.setFieldsValue(
      role
        ? {
            name: role.name,
            display_name: role.display_name,
            description: role.description,
            is_active: role.is_active,
            permissions: role.permissions,
          }
        : { is_active: true, permissions: [] },
    )
  }, [open, role, form])

  // Non-super-admins can only grant permissions they hold (the API enforces this too).
  const grantable = (code) =>
    me.is_super_admin || me.permissions.includes(code) || role?.permissions.includes(code)

  const mutation = useMutation({
    mutationFn: (values) => {
      const body = {
        display_name: values.display_name,
        description: values.description || null,
        permissions: values.permissions || [],
      }
      if (!editing) return rolesApi.create({ ...body, name: values.name })
      if (!role.is_system) body.name = values.name
      body.is_active = values.is_active
      return rolesApi.update(role.id, body)
    },
    onSuccess: (saved) => {
      message.success(`${saved.display_name} saved`)
      queryClient.invalidateQueries({ queryKey: ['roles'] })
      onClose()
    },
    onError: (error) => {
      if (!applyFieldErrors(form, error)) message.error(errorMessage(error))
    },
  })

  const selected = Form.useWatch('permissions', form) || []
  const setModule = (codes, checked) => {
    const others = selected.filter((c) => !codes.includes(c))
    form.setFieldValue('permissions', checked ? [...others, ...codes.filter(grantable)] : others)
  }

  return (
    <Drawer
      title={editing ? `Edit role: ${role.display_name}` : 'New role'}
      open={open}
      onClose={onClose}
      size="large"
      destroyOnHidden
      extra={
        <Space>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="primary" loading={mutation.isPending} onClick={() => form.submit()}>
            Save
          </Button>
        </Space>
      }
    >
      <Form form={form} layout="vertical" onFinish={mutation.mutate} requiredMark="optional">
        {role?.is_system && (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            title="System role: it cannot be renamed or deactivated, but its permissions can change."
          />
        )}
        <Row gutter={16}>
          <Col xs={24} sm={12}>
            <Form.Item
              name="name"
              label="Code"
              extra="Uppercase, e.g. WAREHOUSE_SUPERVISOR"
              normalize={(v) => (v || '').toUpperCase()}
              rules={[
                { required: true, message: 'Enter a code' },
                { pattern: /^[A-Z][A-Z0-9_]{2,49}$/, message: '3–50 characters: A–Z, 0–9 or _' },
              ]}
            >
              <Input disabled={role?.is_system} />
            </Form.Item>
          </Col>
          <Col xs={24} sm={12}>
            <Form.Item
              name="display_name"
              label="Name"
              rules={[{ required: true, min: 2, message: 'Enter a name' }]}
            >
              <Input />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item name="description" label="Description">
          <Input.TextArea rows={2} maxLength={1000} />
        </Form.Item>
        {editing && (
          <Form.Item name="is_active" label="Active" valuePropName="checked">
            <Switch disabled={role.is_system} />
          </Form.Item>
        )}
        <Form.Item name="permissions" label="Permissions" style={{ marginBottom: 0 }}>
          {permissions.isLoading ? (
            <Spin />
          ) : (
            <Checkbox.Group style={{ width: '100%' }}>
              <Row gutter={[12, 12]} style={{ width: '100%' }}>
                {modules.map(([module, perms]) => {
                  const codes = perms.map((p) => p.code)
                  const chosen = codes.filter((c) => selected.includes(c))
                  return (
                    <Col xs={24} md={12} key={module}>
                      <Card
                        size="small"
                        title={
                          <Checkbox
                            checked={chosen.length === codes.length}
                            indeterminate={chosen.length > 0 && chosen.length < codes.length}
                            onChange={(e) => setModule(codes, e.target.checked)}
                          >
                            {humanize(module)}
                          </Checkbox>
                        }
                      >
                        <Space orientation="vertical" size={4}>
                          {perms.map((p) => (
                            <Tooltip
                              key={p.code}
                              title={grantable(p.code) ? p.code : 'You cannot grant a permission you do not have'}
                            >
                              <Checkbox value={p.code} disabled={!grantable(p.code)}>
                                {p.description}
                              </Checkbox>
                            </Tooltip>
                          ))}
                        </Space>
                      </Card>
                    </Col>
                  )
                })}
              </Row>
            </Checkbox.Group>
          )}
        </Form.Item>
      </Form>
    </Drawer>
  )
}
