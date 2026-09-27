import { App, Form, Input, Modal, Typography } from 'antd'
import { useMutation } from '@tanstack/react-query'
import { usersApi } from '../../api/endpoints'
import { applyFieldErrors, errorMessage } from '../../api/errors'
import { PASSWORD_HINT, matchesField, passwordRule } from '../../utils/password'

export default function ResetPasswordModal({ open, user, onClose }) {
  const [form] = Form.useForm()
  const { message } = App.useApp()

  const mutation = useMutation({
    mutationFn: ({ new_password }) => usersApi.resetPassword(user.id, new_password),
    onSuccess: () => {
      message.success(`Password of ${user.full_name} reset. Their sessions have ended.`)
      onClose()
    },
    onError: (error) => {
      if (!applyFieldErrors(form, error)) message.error(errorMessage(error))
    },
  })

  return (
    <Modal
      title={user ? `Reset password for ${user.full_name}` : 'Reset password'}
      open={open}
      onCancel={onClose}
      onOk={() => form.submit()}
      okText="Reset password"
      okButtonProps={{ danger: true }}
      confirmLoading={mutation.isPending}
      destroyOnHidden
    >
      <Typography.Paragraph type="secondary">
        The user will be signed out everywhere. Give them the new password securely and ask them to
        change it after signing in.
      </Typography.Paragraph>
      <Form form={form} layout="vertical" onFinish={mutation.mutate} requiredMark={false}>
        <Form.Item
          name="new_password"
          label="New password"
          extra={PASSWORD_HINT}
          rules={[{ required: true, message: 'Enter a new password' }, passwordRule]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          name="confirm"
          label="Repeat new password"
          dependencies={['new_password']}
          rules={[{ required: true, message: 'Repeat the password' }, matchesField('new_password')]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
      </Form>
    </Modal>
  )
}
