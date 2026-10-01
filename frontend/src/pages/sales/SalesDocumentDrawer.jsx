import { useEffect, useEffectEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Drawer,
  Form,
  Input,
  InputNumber,
  Row,
  Space,
  Switch,
  Typography,
} from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  customersApi,
  invoicesApi,
  productsApi,
  quotationsApi,
  settingsApi,
  warehousesApi,
} from '../../api/endpoints'
import { applyFieldErrors, errorMessage } from '../../api/errors'
import { useAuth } from '../../auth/AuthContext'
import RemoteSelect from '../../components/RemoteSelect'
import { fromApiDate, toApiDate } from '../../utils/dates'
import { formatMoney } from '../../utils/format'
import { documentTotals, lineAmounts } from '../../utils/pricing'

const customerLabel = (c) => `${c.code} · ${c.name}`
const productLabel = (p) => `${p.sku} · ${p.name}`
const warehouseLabel = (w) => `${w.code} · ${w.name}`
const decimal = (v) => (v === null || v === undefined || v === '' ? null : String(v))

const KINDS = {
  quotation: {
    api: quotationsApi,
    queryKey: 'quotations',
    noun: 'quotation',
    dateField: 'quote_date',
    dateLabel: 'Quotation date',
    untilField: 'valid_until',
    untilLabel: 'Valid until',
    untilHelp: 'Empty = the standard validity period',
  },
  invoice: {
    api: invoicesApi,
    queryKey: 'invoices',
    noun: 'invoice',
    dateField: 'invoice_date',
    dateLabel: 'Invoice date',
    untilField: 'due_date',
    untilLabel: 'Due date',
    untilHelp: "Empty = the customer's payment terms",
  },
}

function toFormValues(doc, kind) {
  const k = KINDS[kind]
  return {
    customer_id: doc.customer.id,
    [k.dateField]: fromApiDate(doc[k.dateField]),
    [k.untilField]: fromApiDate(doc[k.untilField]),
    warehouse_id: doc.warehouse_id || undefined,
    customer_reference: doc.customer_reference,
    prices_include_tax: doc.prices_include_tax,
    notes: doc.notes,
    lines: doc.lines.map((l) => ({
      product_id: l.product.id,
      description: l.description,
      quantity: Number(l.quantity),
      unit_price: Number(l.unit_price),
      discount_percent: Number(l.discount_percent),
      tax_rate: Number(l.tax_rate),
    })),
  }
}

/** Create or edit a quotation or invoice (kind = "quotation" | "invoice"). */
export default function SalesDocumentDrawer({ kind, open, document: doc, onClose, onSaved }) {
  const k = KINDS[kind]
  const [form] = Form.useForm()
  const { message } = App.useApp()
  const { can } = useAuth()
  const queryClient = useQueryClient()
  const editing = Boolean(doc)

  const settings = useQuery({
    queryKey: ['settings'],
    queryFn: settingsApi.get,
    enabled: open && can('settings.view'),
  })
  const defaultInclusive = settings.data ? settings.data.prices_include_tax : true

  // Fill the form when the drawer opens (not on every re-render, which would wipe typing).
  const fillForm = useEffectEvent(() => {
    form.resetFields()
    form.setFieldsValue(
      doc
        ? toFormValues(doc, kind)
        : {
            [k.dateField]: dayjs(),
            prices_include_tax: defaultInclusive,
            lines: [{ quantity: 1, discount_percent: 0 }],
          },
    )
  })
  useEffect(() => {
    if (open) fillForm()
  }, [open, doc])

  // For new documents, apply the company setting once it has loaded (unless already changed).
  useEffect(() => {
    if (open && !doc && settings.data && !form.isFieldTouched('prices_include_tax')) {
      form.setFieldValue('prices_include_tax', settings.data.prices_include_tax)
    }
  }, [open, doc, settings.data, form])

  const inclusive = Form.useWatch('prices_include_tax', form) ?? true
  const lines = Form.useWatch('lines', form) || []
  const computed = lines.map((l) =>
    lineAmounts(
      {
        quantity: l?.quantity,
        unitPrice: l?.unit_price,
        discountPercent: l?.discount_percent,
        taxRate: l?.tax_rate,
      },
      inclusive,
    ),
  )
  const totals = documentTotals(computed, inclusive)

  const mutation = useMutation({
    mutationFn: (values) => {
      const body = {
        customer_id: values.customer_id,
        [k.dateField]: toApiDate(values[k.dateField]),
        [k.untilField]: toApiDate(values[k.untilField]),
        customer_reference: values.customer_reference || null,
        notes: values.notes || null,
        lines: values.lines.map((l) => ({
          product_id: l.product_id,
          description: l.description || null,
          quantity: String(l.quantity),
          unit_price: decimal(l.unit_price),
          discount_percent: String(l.discount_percent || 0),
          tax_rate: decimal(l.tax_rate),
        })),
      }
      // New documents follow the system setting unless the switch was changed.
      if (editing || form.isFieldTouched('prices_include_tax') || settings.data) {
        body.prices_include_tax = values.prices_include_tax
      }
      if (kind === 'invoice') body.warehouse_id = values.warehouse_id || null
      if (!editing) {
        if (!body[k.untilField]) delete body[k.untilField]
      }
      return editing ? k.api.update(doc.id, body) : k.api.create(body)
    },
    onSuccess: (saved) => {
      if (editing) message.success(`${k.noun[0].toUpperCase()}${k.noun.slice(1)} saved`)
      else if (kind === 'quotation') message.success(`Quotation ${saved.quote_number} created`)
      else message.success('Draft invoice created')
      queryClient.invalidateQueries({ queryKey: [k.queryKey] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      onSaved?.(saved)
      onClose()
    },
    onError: (error) => {
      if (!applyFieldErrors(form, error)) message.error(errorMessage(error))
    },
  })

  const fillFromProduct = (index, product) => {
    if (!product) return
    const current = form.getFieldValue(['lines', index]) || {}
    form.setFieldValue(['lines', index], {
      ...current,
      unit_price: Number(product.selling_price),
      tax_rate: Number(product.tax_rate),
      description: product.name,
    })
  }

  const title = editing
    ? `Edit ${k.noun} ${doc.quote_number || doc.invoice_number || '(draft)'}`
    : `New ${k.noun}`

  return (
    <Drawer
      title={title}
      open={open}
      onClose={onClose}
      size={1080}
      destroyOnHidden
      extra={
        <Space>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="primary" loading={mutation.isPending} onClick={() => form.submit()}>
            {editing ? 'Save' : `Create ${k.noun}`}
          </Button>
        </Space>
      }
    >
      <Form form={form} layout="vertical" onFinish={mutation.mutate} requiredMark="optional">
        {!editing && (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            title={
              kind === 'quotation'
                ? 'The quotation number (QUO-YYYY-00001, -00002...) is given automatically when you save.'
                : 'The invoice number (INV-YYYY-00001...) is given automatically when the invoice is approved and issued, so issued invoices have no gaps.'
            }
          />
        )}
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item name="customer_id" label="Customer" rules={[{ required: true }]}>
              <RemoteSelect
                queryKey={['customers']}
                fetcher={customersApi.list}
                extraParams={{ is_active: true }}
                labelOf={customerLabel}
                selected={doc?.customer}
                placeholder="Choose the customer"
              />
            </Form.Item>
          </Col>
          <Col xs={12} md={6}>
            <Form.Item name={k.dateField} label={k.dateLabel} rules={[{ required: true }]}>
              <DatePicker style={{ width: '100%' }} format="DD/MM/YYYY" />
            </Form.Item>
          </Col>
          <Col xs={12} md={6}>
            <Form.Item name={k.untilField} label={k.untilLabel} extra={editing ? null : k.untilHelp}>
              <DatePicker style={{ width: '100%' }} format="DD/MM/YYYY" />
            </Form.Item>
          </Col>
          <Col xs={24} md={kind === 'invoice' ? 6 : 12}>
            <Form.Item name="customer_reference" label="Customer order no.">
              <Input placeholder="Their purchase order number" />
            </Form.Item>
          </Col>
          {kind === 'invoice' && (
            <Col xs={24} md={6}>
              <Form.Item
                name="warehouse_id"
                label="Issue goods from"
                extra="Needed before issuing if there are goods"
              >
                <RemoteSelect
                  queryKey={['warehouses']}
                  fetcher={warehousesApi.list}
                  extraParams={{ is_active: true }}
                  labelOf={warehouseLabel}
                  placeholder="Warehouse"
                />
              </Form.Item>
            </Col>
          )}
          <Col xs={24} md={12}>
            <Form.Item
              name="prices_include_tax"
              label="Prices include VAT"
              valuePropName="checked"
              extra={inclusive ? 'VAT is worked out of the prices you enter.' : 'VAT is added on top of the prices.'}
            >
              <Switch />
            </Form.Item>
          </Col>
        </Row>

        <Typography.Text strong>Items</Typography.Text>
        <Form.List
          name="lines"
          rules={[
            {
              validator: (_r, value) =>
                value?.length ? Promise.resolve() : Promise.reject(new Error('Add at least one item')),
            },
          ]}
        >
          {(fields, { add, remove }, { errors }) => (
            <div style={{ marginTop: 8 }}>
              <Row gutter={8} style={{ fontSize: 12, color: '#6b7c93', marginBottom: 4 }}>
                <Col span={6}>Product</Col>
                <Col span={6}>Description</Col>
                <Col span={2}>Qty</Col>
                <Col span={3}>{inclusive ? 'Price (incl VAT)' : 'Price (excl VAT)'}</Col>
                <Col span={2}>Disc %</Col>
                <Col span={2}>VAT %</Col>
                <Col span={2} style={{ textAlign: 'right' }}>
                  Total
                </Col>
              </Row>
              {fields.map((field, index) => (
                <Row gutter={8} key={field.key} align="top">
                  <Col span={6}>
                    <Form.Item name={[field.name, 'product_id']} rules={[{ required: true, message: 'Choose a product' }]}>
                      <RemoteSelect
                        queryKey={['products']}
                        fetcher={productsApi.list}
                        extraParams={{ is_active: true }}
                        labelOf={productLabel}
                        selected={doc?.lines?.[index]?.product}
                        placeholder="Product"
                        onChange={(value, option) => {
                          form.setFieldValue(['lines', field.name, 'product_id'], value)
                          fillFromProduct(field.name, option?.item)
                        }}
                      />
                    </Form.Item>
                  </Col>
                  <Col span={6}>
                    <Form.Item name={[field.name, 'description']}>
                      <Input placeholder="Description" />
                    </Form.Item>
                  </Col>
                  <Col span={2}>
                    <Form.Item name={[field.name, 'quantity']} rules={[{ required: true, message: 'Qty' }]}>
                      <InputNumber min={0.001} precision={3} style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                  <Col span={3}>
                    <Form.Item name={[field.name, 'unit_price']} rules={[{ required: true, message: 'Price' }]}>
                      <InputNumber min={0} precision={2} style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                  <Col span={2}>
                    <Form.Item name={[field.name, 'discount_percent']}>
                      <InputNumber min={0} max={100} precision={2} style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                  <Col span={2}>
                    <Form.Item name={[field.name, 'tax_rate']}>
                      <InputNumber min={0} max={100} precision={2} style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                  <Col span={2} style={{ textAlign: 'right', paddingTop: 5 }}>
                    {formatMoney(computed[index]?.total ?? 0, '')}
                  </Col>
                  <Col span={1}>
                    <Button
                      type="text"
                      danger
                      icon={<DeleteOutlined />}
                      aria-label="Remove item"
                      disabled={fields.length === 1}
                      onClick={() => remove(field.name)}
                    />
                  </Col>
                </Row>
              ))}
              <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ quantity: 1, discount_percent: 0 })}>
                Add item
              </Button>
              <Form.ErrorList errors={errors} />
            </div>
          )}
        </Form.List>

        <Row gutter={16} style={{ marginTop: 20 }}>
          <Col xs={24} md={14}>
            <Form.Item name="notes" label="Notes (printed on the document)">
              <Input.TextArea rows={4} maxLength={2000} />
            </Form.Item>
          </Col>
          <Col xs={24} md={10}>
            <Card size="small" style={{ background: '#f5f9fe' }}>
              <Descriptions column={1} size="small">
                <Descriptions.Item label="Total (excl VAT)">{formatMoney(totals.subtotal)}</Descriptions.Item>
                <Descriptions.Item label="VAT">{formatMoney(totals.tax)}</Descriptions.Item>
                <Descriptions.Item label="Discount">{formatMoney(totals.discount)}</Descriptions.Item>
                <Descriptions.Item label={<strong>Total (incl VAT)</strong>}>
                  <strong>{formatMoney(totals.total)}</strong>
                </Descriptions.Item>
              </Descriptions>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                Estimate while you type; the saved figures are final.
              </Typography.Text>
            </Card>
          </Col>
        </Row>
      </Form>
    </Drawer>
  )
}
