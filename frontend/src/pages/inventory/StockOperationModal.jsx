import { useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { App, Button, Col, Form, Input, InputNumber, Modal, Row, Segmented, Space, Typography } from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { inventoryApi, productsApi, warehousesApi } from '../../api/endpoints'
import { applyFieldErrors, errorMessage } from '../../api/errors'
import RemoteSelect from '../../components/RemoteSelect'

export const warehouseLabel = (w) => `${w.code} · ${w.name}`
export const productLabel = (p) => `${p.sku} · ${p.name}`

function ProductPicker(props) {
  return (
    <RemoteSelect
      queryKey={['products']}
      fetcher={productsApi.list}
      extraParams={{ product_type: 'GOODS', is_active: true }}
      labelOf={productLabel}
      placeholder="Product"
      {...props}
    />
  )
}

function WarehousePicker(props) {
  return (
    <RemoteSelect
      queryKey={['warehouses']}
      fetcher={warehousesApi.list}
      extraParams={{ is_active: true }}
      labelOf={warehouseLabel}
      placeholder="Warehouse"
      {...props}
    />
  )
}

/** Stock adjustment (mode="adjust") or transfer between warehouses (mode="transfer"). */
export default function StockOperationModal({ mode, open, onClose }) {
  const [form] = Form.useForm()
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const transfer = mode === 'transfer'
  const adjustKind = Form.useWatch('kind', form) || 'change'

  useEffect(() => {
    if (!open) return
    form.resetFields()
    form.setFieldsValue({ kind: 'change', lines: [{}] })
  }, [open, form])

  const mutation = useMutation({
    mutationFn: (values) => {
      if (transfer) {
        return inventoryApi.transfer({
          from_warehouse_id: values.from_warehouse_id,
          to_warehouse_id: values.to_warehouse_id,
          notes: values.notes || null,
          lines: values.lines.map((l) => ({ product_id: l.product_id, quantity: String(l.quantity) })),
        })
      }
      return inventoryApi.adjust({
        warehouse_id: values.warehouse_id,
        reason: values.reason,
        lines: values.lines.map((l) =>
          values.kind === 'count'
            ? { product_id: l.product_id, counted_quantity: String(l.quantity) }
            : { product_id: l.product_id, quantity_change: String(l.quantity) },
        ),
      })
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['inventory'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      modal.success({
        title: transfer ? 'Stock transferred' : 'Stock adjusted',
        content: `Reference ${result.reference_number} · ${result.movements.length} movement(s) recorded.`,
      })
      onClose()
    },
    onError: (error) => {
      if (!applyFieldErrors(form, error)) message.error(errorMessage(error))
    },
  })

  return (
    <Modal
      title={transfer ? 'Transfer stock' : 'Adjust stock'}
      open={open}
      onCancel={onClose}
      onOk={() => form.submit()}
      okText={transfer ? 'Transfer' : 'Post adjustment'}
      confirmLoading={mutation.isPending}
      width={760}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" onFinish={mutation.mutate} requiredMark={false}>
        {transfer ? (
          <Row gutter={16}>
            <Col xs={24} sm={12}>
              <Form.Item name="from_warehouse_id" label="From" rules={[{ required: true }]}>
                <WarehousePicker />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item
                name="to_warehouse_id"
                label="To"
                dependencies={['from_warehouse_id']}
                rules={[
                  { required: true },
                  ({ getFieldValue }) => ({
                    validator: (_r, v) =>
                      v && v === getFieldValue('from_warehouse_id')
                        ? Promise.reject(new Error('Choose a different warehouse'))
                        : Promise.resolve(),
                  }),
                ]}
              >
                <WarehousePicker />
              </Form.Item>
            </Col>
          </Row>
        ) : (
          <Row gutter={16}>
            <Col xs={24} sm={12}>
              <Form.Item name="warehouse_id" label="Warehouse" rules={[{ required: true }]}>
                <WarehousePicker />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item name="kind" label="Enter">
                <Segmented
                  block
                  options={[
                    { value: 'change', label: 'Change (+/−)' },
                    { value: 'count', label: 'Counted quantity' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="reason" label="Reason" rules={[{ required: true, min: 3 }]}>
                <Input placeholder="e.g. Monthly stock count, breakage, opening balance" />
              </Form.Item>
            </Col>
          </Row>
        )}

        <Typography.Text strong>Lines</Typography.Text>
        {!transfer && (
          <Typography.Paragraph type="secondary" style={{ marginBottom: 8 }}>
            {adjustKind === 'count'
              ? 'Enter what you physically counted; the system works out the difference.'
              : 'Use a negative number to remove stock, e.g. -2 for two damaged bags.'}
          </Typography.Paragraph>
        )}
        <Form.List
          name="lines"
          rules={[
            {
              validator: (_r, lines) =>
                lines?.length ? Promise.resolve() : Promise.reject(new Error('Add at least one line')),
            },
          ]}
        >
          {(fields, { add, remove }, { errors }) => (
            <>
              {fields.map((field) => (
                <Space key={field.key} align="start" style={{ display: 'flex', marginBottom: 4 }}>
                  <Form.Item
                    name={[field.name, 'product_id']}
                    rules={[{ required: true, message: 'Choose a product' }]}
                    style={{ width: 430, marginBottom: 8 }}
                  >
                    <ProductPicker />
                  </Form.Item>
                  <Form.Item
                    name={[field.name, 'quantity']}
                    rules={[
                      { required: true, message: 'Quantity' },
                      {
                        validator: (_r, v) => {
                          if (v === null || v === undefined) return Promise.resolve()
                          if (transfer && v <= 0) return Promise.reject(new Error('Must be above 0'))
                          if (!transfer && adjustKind === 'change' && Number(v) === 0) {
                            return Promise.reject(new Error('Cannot be 0'))
                          }
                          if (!transfer && adjustKind === 'count' && v < 0) {
                            return Promise.reject(new Error('Cannot be negative'))
                          }
                          return Promise.resolve()
                        },
                      },
                    ]}
                    style={{ width: 170, marginBottom: 8 }}
                  >
                    <InputNumber precision={3} placeholder="Quantity" style={{ width: '100%' }} />
                  </Form.Item>
                  <Button
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    aria-label="Remove line"
                    disabled={fields.length === 1}
                    onClick={() => remove(field.name)}
                  />
                </Space>
              ))}
              <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({})}>
                Add line
              </Button>
              <Form.ErrorList errors={errors} />
            </>
          )}
        </Form.List>
        {transfer && (
          <Form.Item name="notes" label="Notes" style={{ marginTop: 16 }}>
            <Input.TextArea rows={2} />
          </Form.Item>
        )}
      </Form>
    </Modal>
  )
}
