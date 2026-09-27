import { useEffect } from 'react'
import { App, Col, Form, Input, Modal, Row, Select } from 'antd'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { usersApi } from '../../api/endpoints'
import { applyFieldErrors, errorMessage } from '../../api/errors'
import { useAuth } from '../../auth/AuthContext'
import { PASSWORD_HINT, matchesField, passwordRule } from '../../utils/password'

/** Create a user (user = null) or edit an existing user's profile. */
export default function UserFormModal({ open, user, roles, onClose }) {
  const [form] = Form.useForm()
  const { message } = App.useApp()
  const { can } = useAuth()
  const queryClient = useQueryClient()
  const editing = Boolean(user)
  const canAssignRoles = can('users.assign_roles')

  useEffect(() => {
    if (!open) return
    form.resetFields()
    if (user) {
      form.setFieldsValue({
        full_name: user.full_name,
        username: user.username,
        email: user.email,
        phone: user.phone,
      })
    }
  }, [open, user, form])

  const mutation = useMutation({
    mutationFn: (values) => {
      const { confirm: _confirm, ...body } = values
      if (body.phone === '') body.phone = null
      return editing ? usersApi.update(user.id, body) : usersApi.create(body)
    },
    onSuccess: (saved) => {
      message.success(editing ? `${saved.full_name} updated` : `${saved.full_name} created`)
      queryClient.invalidateQueries({ queryKey: ['users'] })
      onClose()
    },
    onError: (error) => {
      if (!applyFieldErrors(form, error)) message.error(errorMessage(error))
    },
  })

  return (
    <Modal
      title={editing ? `Edit ${user.full_name}` : 'New user'}
      open={open}
      onCancel={onClose}
      onOk={() => form.submit()}
      okText={editing ? 'Save changes' : 'Create user'}
      confirmLoading={mutation.isPending}
      width={620}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" onFinish={mutation.mutate} requiredMark="optional">
        <Row gutter={16}>
          <Col xs={24} sm={12}>
            <Form.Item
              name="full_name"
              label="Full name"
              rules={[{ required: true, min: 2, message: 'Enter the full name' }]}
            >
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} sm={12}>
            <Form.Item
              name="username"
              label="Username"
              extra="Lowercase letters, digits, dots, dashes or underscores."
              rules={[
                { required: true, message: 'Enter a username' },
                {
                  pattern: /^[a-zA-Z0-9][a-zA-Z0-9._-]{1,48}[a-zA-Z0-9]$/,
                  message: '3–50 characters: letters, digits, ".", "_" or "-"',
                },
              ]}
            >
              <Input autoComplete="off" />
            </Form.Item>
          </Col>
          <Col xs={24} sm={12}>
            <Form.Item
              name="email"
              label="Email"
              rules={[
                { required: true, message: 'Enter an email address' },
                { type: 'email', message: 'Enter a valid email address' },
              ]}
            >
              <Input autoComplete="off" />
            </Form.Item>
          </Col>
          <Col xs={24} sm={12}>
            <Form.Item name="phone" label="Phone">
              <Input placeholder="+260 97 1234567" />
            </Form.Item>
          </Col>
        </Row>
        {!editing && (
          <>
            <Row gutter={16}>
              <Col xs={24} sm={12}>
                <Form.Item
                  name="password"
                  label="Initial password"
                  extra={PASSWORD_HINT}
                  rules={[{ required: true, message: 'Enter a password' }, passwordRule]}
                >
                  <Input.Password autoComplete="new-password" />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item
                  name="confirm"
                  label="Repeat password"
                  dependencies={['password']}
                  rules={[{ required: true, message: 'Repeat the password' }, matchesField('password')]}
                >
                  <Input.Password autoComplete="new-password" />
                </Form.Item>
              </Col>
            </Row>
            {canAssignRoles && (
              <Form.Item name="role_ids" label="Roles">
                <Select
                  mode="multiple"
                  allowClear
                  placeholder="Choose roles"
                  showSearch={{ optionFilterProp: 'label' }}
                  options={(roles || [])
                    .filter((r) => r.is_active)
                    .map((r) => ({ value: r.id, label: r.display_name }))}
                />
              </Form.Item>
            )}
          </>
        )}
      </Form>
    </Modal>
  )
}
