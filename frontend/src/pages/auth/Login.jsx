import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Alert, Button, Form, Input } from 'antd'
import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { useAuth } from '../../auth/AuthContext'
import { errorMessage } from '../../api/errors'
import AuthShell from './AuthShell'

export default function Login() {
  const { login, status, expired } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const destination = location.state?.from?.pathname || '/dashboard'
  if (status === 'authenticated') return <Navigate to={destination} replace />

  const onFinish = async ({ identifier, password }) => {
    setError(null)
    setSubmitting(true)
    try {
      await login(identifier, password)
      navigate(destination, { replace: true })
    } catch (err) {
      setError(errorMessage(err, 'Sign-in failed. Please try again.'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell title="Sign in" subtitle="Use your email address or username.">
      {expired && !error && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          title="Your session has ended. Please sign in again."
        />
      )}
      {error && <Alert type="error" showIcon style={{ marginBottom: 16 }} title={error} />}
      <Form layout="vertical" onFinish={onFinish} requiredMark={false} disabled={submitting}>
        <Form.Item
          name="identifier"
          label="Email or username"
          rules={[{ required: true, message: 'Enter your email or username' }]}
        >
          <Input prefix={<UserOutlined />} autoComplete="username" autoFocus size="large" />
        </Form.Item>
        <Form.Item
          name="password"
          label="Password"
          rules={[{ required: true, message: 'Enter your password' }]}
        >
          <Input.Password prefix={<LockOutlined />} autoComplete="current-password" size="large" />
        </Form.Item>
        <Button type="primary" htmlType="submit" block size="large" loading={submitting}>
          Sign in
        </Button>
      </Form>
      <div style={{ textAlign: 'center', marginTop: 16 }}>
        <Link to="/forgot-password">Forgot your password?</Link>
      </div>
    </AuthShell>
  )
}
