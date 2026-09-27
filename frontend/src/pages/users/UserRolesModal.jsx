import { useEffect } from 'react'
import { App, Form, Modal, Select, Typography } from 'antd'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { usersApi } from '../../api/endpoints'
import { errorMessage } from '../../api/errors'

export default function UserRolesModal({ open, user, roles, onClose }) {
  const [form] = Form.useForm()
  const { message } = App.useApp()
  const queryClient = useQueryClient()

  useEffect(() => {
    if (open && user) form.setFieldsValue({ role_ids: user.roles.map((r) => r.id) })
  }, [open, user, form])

  const mutation = useMutation({
    mutationFn: ({ role_ids }) => usersApi.setRoles(user.id, role_ids || []),
    onSuccess: (saved) => {
      message.success(`Roles of ${saved.full_name} updated`)
      queryClient.invalidateQueries({ queryKey: ['users'] })
      queryClient.invalidateQueries({ queryKey: ['roles'] })
      onClose()
    },
    onError: (error) => message.error(errorMessage(error)),
  })

  return (
    <Modal
      title={user ? `Roles of ${user.full_name}` : 'Roles'}
      open={open}
      onCancel={onClose}
      onOk={() => form.submit()}
      okText="Save roles"
      confirmLoading={mutation.isPending}
      destroyOnHidden
    >
      <Typography.Paragraph type="secondary">
        Changes apply immediately, without the user signing in again. You can only give roles whose
        permissions you hold yourself.
      </Typography.Paragraph>
      <Form form={form} layout="vertical" onFinish={mutation.mutate}>
        <Form.Item name="role_ids" label="Roles">
          <Select
            mode="multiple"
            allowClear
            optionFilterProp="label"
            options={(roles || []).map((r) => ({
              value: r.id,
              label: r.display_name,
              disabled: !r.is_active,
            }))}
          />
        </Form.Item>
      </Form>
    </Modal>
  )
}
