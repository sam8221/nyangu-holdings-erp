import { useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, App, Button, Card, Col, Form, Input, InputNumber, Row, Skeleton, Switch } from 'antd'
import { settingsApi } from '../../api/endpoints'
import { applyFieldErrors, errorMessage } from '../../api/errors'
import { useAuth } from '../../auth/AuthContext'
import PageHeader from '../../components/PageHeader'

export default function SettingsPage() {
  const { can } = useAuth()
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const queryClient = useQueryClient()
  const editable = can('settings.update')
  const settings = useQuery({ queryKey: ['settings'], queryFn: settingsApi.get })

  useEffect(() => {
    if (settings.data) form.setFieldsValue(settings.data)
  }, [settings.data, form])

  const save = useMutation({
    mutationFn: (values) =>
      settingsApi.update({ ...values, default_vat_rate: String(values.default_vat_rate) }),
    onSuccess: (data) => {
      message.success('Settings saved')
      queryClient.setQueryData(['settings'], data)
    },
    onError: (error) => {
      if (!applyFieldErrors(form, error)) message.error(errorMessage(error))
    },
  })

  return (
    <>
      <PageHeader title="Settings" subtitle="Defaults used across the system." />
      {settings.isError && <Alert type="error" showIcon title={errorMessage(settings.error)} />}
      {settings.isLoading ? (
        <Skeleton active />
      ) : (
        <Card style={{ maxWidth: 760 }}>
          <Form form={form} layout="vertical" onFinish={save.mutate} disabled={!editable}>
            <Row gutter={16}>
              <Col xs={24} sm={12}>
                <Form.Item
                  name="default_vat_rate"
                  label="Default VAT rate (%)"
                  extra="Applied to new products. Zambia's standard rate is 16%."
                  rules={[{ required: true }]}
                >
                  <InputNumber min={0} max={100} step={0.5} precision={2} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item
                  name="default_payment_terms_days"
                  label="Default payment terms (days)"
                  extra="Used for new customers and suppliers."
                  rules={[{ required: true }]}
                >
                  <InputNumber min={0} max={365} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item
                  name="annual_leave_days"
                  label="Annual leave entitlement (days per year)"
                  rules={[{ required: true }]}
                >
                  <InputNumber min={0} max={366} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item
                  name="low_stock_alerts_enabled"
                  label="Low-stock alerts"
                  valuePropName="checked"
                  extra="Notify inventory staff when a product falls to its reorder level."
                >
                  <Switch />
                </Form.Item>
              </Col>
              <Col span={24}>
                <Form.Item name="invoice_footer" label="Invoice footer" extra="Printed at the bottom of invoices.">
                  <Input.TextArea rows={2} maxLength={500} showCount />
                </Form.Item>
              </Col>
            </Row>
            {editable && (
              <Button type="primary" htmlType="submit" loading={save.isPending}>
                Save settings
              </Button>
            )}
          </Form>
        </Card>
      )}
    </>
  )
}
