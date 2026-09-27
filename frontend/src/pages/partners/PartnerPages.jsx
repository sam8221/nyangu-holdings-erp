import { useState } from 'react'
import { Col, Divider, Form, Input, InputNumber, Row, Select, Switch, Typography } from 'antd'
import { customersApi, suppliersApi } from '../../api/endpoints'
import CrudPage from '../../components/CrudPage'
import { ActiveFilter, ActiveTag, emptyToNull, tpinRule } from '../../components/fields'
import { formatMoney } from '../../utils/format'

const CONTACT_FIELDS = ['tpin', 'email', 'phone', 'address', 'city', 'contact_person', 'notes']

function ContactFields() {
  return (
    <Row gutter={16}>
      <Col xs={24} sm={12}>
        <Form.Item name="tpin" label="TPIN" rules={[tpinRule]}>
          <Input maxLength={10} />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item name="contact_person" label="Contact person">
          <Input />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item name="email" label="Email" rules={[{ type: 'email' }]}>
          <Input />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item name="phone" label="Phone">
          <Input placeholder="+260 ..." />
        </Form.Item>
      </Col>
      <Col xs={24} sm={16}>
        <Form.Item name="address" label="Address">
          <Input />
        </Form.Item>
      </Col>
      <Col xs={24} sm={8}>
        <Form.Item name="city" label="City">
          <Input />
        </Form.Item>
      </Col>
    </Row>
  )
}

function Name({ record }) {
  return (
    <Row gutter={16}>
      <Col span={24}>
        {record && (
          <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
            Code {record.code}
          </Typography.Text>
        )}
        <Form.Item name="name" label="Name" rules={[{ required: true, min: 2 }]}>
          <Input autoFocus />
        </Form.Item>
      </Col>
    </Row>
  )
}

function StatusAndNotes({ editing }) {
  return (
    <>
      <Form.Item name="notes" label="Notes">
        <Input.TextArea rows={2} />
      </Form.Item>
      {editing && (
        <Form.Item name="is_active" label="Active" valuePropName="checked">
          <Switch />
        </Form.Item>
      )}
    </>
  )
}

// ------------------------------------------------------------------ customers
function CustomerFields({ record, editing }) {
  return (
    <>
      <Name record={record} />
      <Row gutter={16}>
        <Col xs={24} sm={8}>
          <Form.Item name="customer_type" label="Type" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'BUSINESS', label: 'Business' },
                { value: 'INDIVIDUAL', label: 'Individual' },
              ]}
            />
          </Form.Item>
        </Col>
        <Col xs={24} sm={8}>
          <Form.Item
            name="credit_limit"
            label="Credit limit (ZMW)"
            extra="Leave empty for no limit"
          >
            <InputNumber min={0} precision={2} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col xs={24} sm={8}>
          <Form.Item name="payment_terms_days" label="Payment terms (days)" extra="Empty = default">
            <InputNumber min={0} max={365} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
      </Row>
      <Divider titlePlacement="start" plain>
        Contact
      </Divider>
      <ContactFields />
      <StatusAndNotes editing={editing} />
    </>
  )
}

const customerPayload = (values, record) => {
  const body = emptyToNull(values, CONTACT_FIELDS)
  body.credit_limit =
    values.credit_limit === null || values.credit_limit === undefined ? null : String(values.credit_limit)
  if (body.payment_terms_days === null || body.payment_terms_days === undefined) {
    if (record) delete body.payment_terms_days
    else body.payment_terms_days = null
  }
  if (!record) delete body.is_active
  return body
}

const customerFormValues = (c) => ({
  ...c,
  credit_limit: c.credit_limit === null ? null : Number(c.credit_limit),
})

export function CustomersPage() {
  const [filters, setFilters] = useState({})
  return (
    <CrudPage
      title="Customers"
      subtitle="Who you sell to, with credit limits and payment terms."
      entityLabel="Customer"
      queryKey={['customers']}
      api={customersApi}
      perms={{ create: 'customers.create', update: 'customers.update', delete: 'customers.delete' }}
      filters={filters}
      filterBar={
        <>
          <Select
            allowClear
            placeholder="Any type"
            style={{ width: 150 }}
            value={filters.customer_type}
            onChange={(customer_type) => setFilters((f) => ({ ...f, customer_type }))}
            options={[
              { value: 'BUSINESS', label: 'Business' },
              { value: 'INDIVIDUAL', label: 'Individual' },
            ]}
          />
          <ActiveFilter
            value={filters.is_active}
            onChange={(is_active) => setFilters((f) => ({ ...f, is_active }))}
          />
        </>
      }
      searchPlaceholder="Search code, name, email, phone or TPIN"
      FormFields={CustomerFields}
      toFormValues={customerFormValues}
      toPayload={customerPayload}
      initialValues={{ customer_type: 'BUSINESS' }}
      formWidth={720}
      describe={(c) => `${c.code} ${c.name}`}
      columns={[
        { title: 'Code', dataIndex: 'code', key: 'code', sortField: 'code' },
        { title: 'Name', dataIndex: 'name', key: 'name', sortField: 'name' },
        {
          title: 'Type',
          dataIndex: 'customer_type',
          key: 'type',
          render: (t) => (t === 'INDIVIDUAL' ? 'Individual' : 'Business'),
        },
        { title: 'Phone', dataIndex: 'phone', key: 'phone', render: (v) => v || '—' },
        { title: 'TPIN', dataIndex: 'tpin', key: 'tpin', render: (v) => v || '—' },
        {
          title: 'Credit limit',
          dataIndex: 'credit_limit',
          key: 'credit_limit',
          sortField: 'credit_limit',
          align: 'right',
          render: (v) => (v === null ? <span className="muted">No limit</span> : formatMoney(v)),
        },
        {
          title: 'Terms',
          dataIndex: 'payment_terms_days',
          key: 'terms',
          align: 'right',
          render: (d) => `${d} days`,
        },
        { title: 'Status', key: 'active', render: (_, c) => <ActiveTag active={c.is_active} /> },
      ]}
    />
  )
}

// ------------------------------------------------------------------ suppliers
function SupplierFields({ record, editing }) {
  return (
    <>
      <Name record={record} />
      <Row gutter={16}>
        <Col xs={24} sm={8}>
          <Form.Item name="payment_terms_days" label="Payment terms (days)" extra="Empty = default">
            <InputNumber min={0} max={365} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
      </Row>
      <Divider titlePlacement="start" plain>
        Contact
      </Divider>
      <ContactFields />
      <Divider titlePlacement="start" plain>
        Bank details
      </Divider>
      <Row gutter={16}>
        <Col xs={24} sm={8}>
          <Form.Item name="bank_name" label="Bank">
            <Input placeholder="e.g. Zanaco" />
          </Form.Item>
        </Col>
        <Col xs={24} sm={8}>
          <Form.Item name="bank_branch" label="Branch">
            <Input />
          </Form.Item>
        </Col>
        <Col xs={24} sm={8}>
          <Form.Item name="bank_account_number" label="Account number">
            <Input />
          </Form.Item>
        </Col>
      </Row>
      <StatusAndNotes editing={editing} />
    </>
  )
}

const supplierPayload = (values, record) => {
  const body = emptyToNull(values, [...CONTACT_FIELDS, 'bank_name', 'bank_branch', 'bank_account_number'])
  if (body.payment_terms_days === null || body.payment_terms_days === undefined) {
    if (record) delete body.payment_terms_days
    else body.payment_terms_days = null
  }
  if (!record) delete body.is_active
  return body
}

export function SuppliersPage() {
  const [active, setActive] = useState()
  return (
    <CrudPage
      title="Suppliers"
      subtitle="Who you buy from, with payment terms and bank details."
      entityLabel="Supplier"
      queryKey={['suppliers']}
      api={suppliersApi}
      perms={{ create: 'suppliers.create', update: 'suppliers.update', delete: 'suppliers.delete' }}
      filters={{ is_active: active }}
      filterBar={<ActiveFilter value={active} onChange={setActive} />}
      searchPlaceholder="Search code, name, email, phone or TPIN"
      FormFields={SupplierFields}
      toPayload={supplierPayload}
      formWidth={720}
      describe={(s) => `${s.code} ${s.name}`}
      columns={[
        { title: 'Code', dataIndex: 'code', key: 'code', sortField: 'code' },
        { title: 'Name', dataIndex: 'name', key: 'name', sortField: 'name' },
        {
          title: 'Contact',
          key: 'contact',
          render: (_, s) => s.contact_person || s.email || s.phone || '—',
        },
        { title: 'Phone', dataIndex: 'phone', key: 'phone', render: (v) => v || '—' },
        { title: 'Bank', key: 'bank', render: (_, s) => s.bank_name || '—' },
        {
          title: 'Terms',
          dataIndex: 'payment_terms_days',
          key: 'terms',
          align: 'right',
          render: (d) => `${d} days`,
        },
        { title: 'Status', key: 'active', render: (_, s) => <ActiveTag active={s.is_active} /> },
      ]}
    />
  )
}
