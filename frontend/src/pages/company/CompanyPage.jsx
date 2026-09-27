import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, App, Button, Card, Col, Form, Input, Row, Select, Skeleton, Switch, Tabs, Tag } from 'antd'
import { branchesApi, companyApi, departmentsApi } from '../../api/endpoints'
import { applyFieldErrors, errorMessage } from '../../api/errors'
import { useAuth } from '../../auth/AuthContext'
import CrudPage from '../../components/CrudPage'
import { ActiveFilter, ActiveTag, MONTHS, emptyToNull, tpinRule, upper } from '../../components/fields'
import PageHeader from '../../components/PageHeader'

const COMPANY_OPTIONAL = [
  'legal_name',
  'registration_number',
  'tpin',
  'vat_number',
  'email',
  'phone',
  'website',
  'address',
  'city',
]

function CompanyProfile() {
  const { can } = useAuth()
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const queryClient = useQueryClient()
  const editable = can('company.update')
  const company = useQuery({ queryKey: ['company'], queryFn: companyApi.get })

  useEffect(() => {
    if (company.data) form.setFieldsValue(company.data)
  }, [company.data, form])

  const save = useMutation({
    mutationFn: (values) => companyApi.update(emptyToNull(values, COMPANY_OPTIONAL)),
    onSuccess: (data) => {
      message.success('Company profile saved')
      queryClient.setQueryData(['company'], data)
    },
    onError: (error) => {
      if (!applyFieldErrors(form, error)) message.error(errorMessage(error))
    },
  })

  if (company.isLoading) return <Skeleton active />
  if (company.isError) return <Alert type="error" showIcon title={errorMessage(company.error)} />

  return (
    <Card>
      <Form
        form={form}
        layout="vertical"
        onFinish={save.mutate}
        disabled={!editable}
        requiredMark="optional"
      >
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item name="name" label="Trading name" rules={[{ required: true, min: 2 }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item name="legal_name" label="Registered name">
              <Input placeholder="e.g. Nyangu Holdings Limited" />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item name="registration_number" label="PACRA registration number">
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item name="tpin" label="TPIN" rules={[tpinRule]}>
              <Input maxLength={10} />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item name="vat_number" label="VAT number">
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item name="email" label="Email" rules={[{ type: 'email' }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item name="phone" label="Phone">
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item name="website" label="Website">
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item name="address" label="Address">
              <Input.TextArea rows={2} />
            </Form.Item>
          </Col>
          <Col xs={12} md={6}>
            <Form.Item name="city" label="City">
              <Input />
            </Form.Item>
          </Col>
          <Col xs={12} md={6}>
            <Form.Item name="country" label="Country" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col xs={12} md={6}>
            <Form.Item
              name="currency"
              label="Currency"
              normalize={upper}
              rules={[{ required: true }, { pattern: /^[A-Z]{3}$/, message: 'Three letters, e.g. ZMW' }]}
            >
              <Input maxLength={3} />
            </Form.Item>
          </Col>
          <Col xs={12} md={6}>
            <Form.Item
              name="fiscal_year_start_month"
              label="Financial year starts"
              rules={[{ required: true }]}
            >
              <Select options={MONTHS} />
            </Form.Item>
          </Col>
        </Row>
        {editable && (
          <Button type="primary" htmlType="submit" loading={save.isPending}>
            Save profile
          </Button>
        )}
      </Form>
    </Card>
  )
}

function BranchFields() {
  return (
    <Row gutter={16}>
      <Col xs={24} sm={8}>
        <Form.Item name="code" label="Code" normalize={upper} rules={[{ required: true }]}>
          <Input placeholder="LSK" maxLength={20} />
        </Form.Item>
      </Col>
      <Col xs={24} sm={16}>
        <Form.Item name="name" label="Name" rules={[{ required: true, min: 2 }]}>
          <Input placeholder="Lusaka head office" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item name="city" label="City">
          <Input />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item name="phone" label="Phone">
          <Input />
        </Form.Item>
      </Col>
      <Col span={24}>
        <Form.Item name="email" label="Email" rules={[{ type: 'email' }]}>
          <Input />
        </Form.Item>
      </Col>
      <Col span={24}>
        <Form.Item name="address" label="Address">
          <Input.TextArea rows={2} />
        </Form.Item>
      </Col>
      <Col xs={12}>
        <Form.Item name="is_head_office" label="Head office" valuePropName="checked">
          <Switch />
        </Form.Item>
      </Col>
      <Col xs={12}>
        <Form.Item name="is_active" label="Active" valuePropName="checked">
          <Switch />
        </Form.Item>
      </Col>
    </Row>
  )
}

const branchPayload = (values, record) => {
  const body = emptyToNull(values, ['address', 'city', 'phone', 'email'])
  if (!record) delete body.is_active // new branches start active
  return body
}

function DepartmentFields() {
  return (
    <Row gutter={16}>
      <Col xs={24} sm={8}>
        <Form.Item name="code" label="Code" normalize={upper} rules={[{ required: true }]}>
          <Input placeholder="FIN" maxLength={20} />
        </Form.Item>
      </Col>
      <Col xs={24} sm={16}>
        <Form.Item name="name" label="Name" rules={[{ required: true, min: 2 }]}>
          <Input placeholder="Finance" />
        </Form.Item>
      </Col>
      <Col span={24}>
        <Form.Item name="description" label="Description">
          <Input.TextArea rows={2} />
        </Form.Item>
      </Col>
      <Col span={24}>
        <Form.Item name="is_active" label="Active" valuePropName="checked">
          <Switch />
        </Form.Item>
      </Col>
    </Row>
  )
}

const departmentPayload = (values, record) => {
  const body = emptyToNull(values, ['description'])
  if (!record) delete body.is_active
  return body
}

const NEW_ACTIVE = { is_active: true, is_head_office: false }

function Branches() {
  const [active, setActive] = useState()
  return (
    <CrudPage
      embedded
      entityLabel="Branch"
      queryKey={['branches']}
      api={branchesApi}
      perms={{ create: 'company.update', update: 'company.update', delete: 'company.update' }}
      filters={{ is_active: active }}
      filterBar={<ActiveFilter value={active} onChange={setActive} />}
      searchPlaceholder="Search code, name or city"
      FormFields={BranchFields}
      toPayload={branchPayload}
      initialValues={NEW_ACTIVE}
      describe={(b) => `${b.code} ${b.name}`}
      columns={[
        { title: 'Code', dataIndex: 'code', key: 'code', sortField: 'code' },
        {
          title: 'Name',
          dataIndex: 'name',
          key: 'name',
          sortField: 'name',
          render: (name, b) => (
            <>
              {name} {b.is_head_office && <Tag color="blue">Head office</Tag>}
            </>
          ),
        },
        { title: 'City', dataIndex: 'city', key: 'city', render: (v) => v || '—' },
        { title: 'Phone', dataIndex: 'phone', key: 'phone', render: (v) => v || '—' },
        { title: 'Status', key: 'active', render: (_, b) => <ActiveTag active={b.is_active} /> },
      ]}
    />
  )
}

function Departments() {
  const [active, setActive] = useState()
  return (
    <CrudPage
      embedded
      entityLabel="Department"
      queryKey={['departments']}
      api={departmentsApi}
      perms={{ create: 'company.update', update: 'company.update', delete: 'company.update' }}
      filters={{ is_active: active }}
      filterBar={<ActiveFilter value={active} onChange={setActive} />}
      searchPlaceholder="Search code or name"
      FormFields={DepartmentFields}
      toPayload={departmentPayload}
      initialValues={NEW_ACTIVE}
      columns={[
        { title: 'Code', dataIndex: 'code', key: 'code', sortField: 'code' },
        { title: 'Name', dataIndex: 'name', key: 'name', sortField: 'name' },
        {
          title: 'Description',
          dataIndex: 'description',
          key: 'description',
          render: (v) => v || '—',
        },
        { title: 'Status', key: 'active', render: (_, d) => <ActiveTag active={d.is_active} /> },
      ]}
    />
  )
}

export default function CompanyPage() {
  return (
    <>
      <PageHeader title="Company" subtitle="Company details, branches and departments." />
      <Tabs
        destroyOnHidden
        items={[
          { key: 'profile', label: 'Profile', children: <CompanyProfile /> },
          { key: 'branches', label: 'Branches', children: <Branches /> },
          { key: 'departments', label: 'Departments', children: <Departments /> },
        ]}
      />
    </>
  )
}
