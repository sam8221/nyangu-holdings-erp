import { App, Form, Input, Modal } from 'antd'
import { useMutation } from '@tanstack/react-query'
import { authApi } from '../api/endpoints'
import { applyFieldErrors, errorMessage } from '../api/errors'
import { saveTokens } from '../api/tokens'
import { PASSWORD_HINT, matchesField, passwordRule } from '../utils/password'

export default function ChangePasswordModal({ open, onClose }) {
  const [form] = Form.useForm()
  const { message } = App.useApp()

  const mutation = useMutation({
    mutationFn: (values) =>
      authApi.changePassword({
        current_password: values.current_password,
        new_password: values.new_password,
      }),
    onSuccess: (tokens) => {
      // Other sessions end; this one continues with the fresh tokens.
      saveTokens(tokens)
      message.success('Password changed. Other devices have been signed out.')
      form.resetFields()
      onClose()
    },
    onError: (error) => {
      if (!applyFieldErrors(form, error)) message.error(errorMessage(error))
    },
  })

  return (
    <Modal
      title="Change password"
      open={open}
      onCancel={onClose}
      onOk={() => form.submit()}
      okText="Change password"
      confirmLoading={mutation.isPending}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" onFinish={mutation.mutate} requiredMark={false}>
        <Form.Item
          name="current_password"
          label="Current password"
          rules={[{ required: true, message: 'Enter your current password' }]}
        >
          <Input.Password autoComplete="current-password" />
        </Form.Item>
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
          rules={[{ required: true, message: 'Repeat the new password' }, matchesField('new_password')]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
      </Form>
    </Modal>
  )
}
