import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Alert, Button, Form, Input, Result } from 'antd'
import { MailOutlined } from '@ant-design/icons'
import { authApi } from '../../api/endpoints'
import { errorMessage } from '../../api/errors'
import AuthShell from './AuthShell'

export default function ForgotPassword() {
  const [sent, setSent] = useState(null)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const onFinish = async ({ email }) => {
    setError(null)
    setSubmitting(true)
    try {
      const response = await authApi.forgotPassword(email)
      setSent(response.message)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  if (sent) {
    return (
      <AuthShell title="Check your email">
        <Result
          status="success"
          style={{ padding: 0 }}
          subTitle={`${sent} The link expires in 30 minutes.`}
          extra={<Link to="/login">Back to sign in</Link>}
        />
      </AuthShell>
    )
  }

  return (
    <AuthShell
      title="Forgot your password?"
      subtitle="Enter your email address and we will send you a link to choose a new one."
    >
      {error && <Alert type="error" showIcon style={{ marginBottom: 16 }} title={error} />}
      <Form layout="vertical" onFinish={onFinish} requiredMark={false} disabled={submitting}>
        <Form.Item
          name="email"
          label="Email address"
          rules={[
            { required: true, message: 'Enter your email address' },
            { type: 'email', message: 'Enter a valid email address' },
          ]}
        >
          <Input prefix={<MailOutlined />} autoComplete="email" autoFocus size="large" />
        </Form.Item>
        <Button type="primary" htmlType="submit" block size="large" loading={submitting}>
          Send reset link
        </Button>
      </Form>
      <div style={{ textAlign: 'center', marginTop: 16 }}>
        <Link to="/login">Back to sign in</Link>
      </div>
    </AuthShell>
  )
}
