import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Alert, Button, Form, Input, Result } from 'antd'
import { authApi } from '../../api/endpoints'
import { errorMessage } from '../../api/errors'
import { PASSWORD_HINT, matchesField, passwordRule } from '../../utils/password'
import AuthShell from './AuthShell'

export default function ResetPassword() {
  const [params] = useSearchParams()
  const token = params.get('token')
  const [done, setDone] = useState(false)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  if (!token) {
    return (
      <AuthShell title="Reset link missing">
        <Result
          status="warning"
          style={{ padding: 0 }}
          subTitle="Open the link from your email again, or request a new one."
          extra={<Link to="/forgot-password">Request a new link</Link>}
        />
      </AuthShell>
    )
  }

  if (done) {
    return (
      <AuthShell title="Password changed">
        <Result
          status="success"
          style={{ padding: 0 }}
          subTitle="You can now sign in with your new password. Other devices have been signed out."
          extra={
            <Link to="/login">
              <Button type="primary">Sign in</Button>
            </Link>
          }
        />
      </AuthShell>
    )
  }

  const onFinish = async ({ new_password }) => {
    setError(null)
    setSubmitting(true)
    try {
      await authApi.resetPassword(token, new_password)
      setDone(true)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell title="Choose a new password">
      {error && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          title={error}
          description={<Link to="/forgot-password">Request a new link</Link>}
        />
      )}
      <Form layout="vertical" onFinish={onFinish} requiredMark={false} disabled={submitting}>
        <Form.Item
          name="new_password"
          label="New password"
          extra={PASSWORD_HINT}
          rules={[{ required: true, message: 'Enter a new password' }, passwordRule]}
        >
          <Input.Password autoComplete="new-password" autoFocus size="large" />
        </Form.Item>
        <Form.Item
          name="confirm"
          label="Repeat new password"
          dependencies={['new_password']}
          rules={[{ required: true, message: 'Repeat the new password' }, matchesField('new_password')]}
        >
          <Input.Password autoComplete="new-password" size="large" />
        </Form.Item>
        <Button type="primary" htmlType="submit" block size="large" loading={submitting}>
          Set new password
        </Button>
      </Form>
    </AuthShell>
  )
}
