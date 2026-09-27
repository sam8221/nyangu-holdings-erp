import { useState } from 'react'
import { Col, Form, Input, Row, Switch } from 'antd'
import { branchesApi, warehousesApi } from '../../api/endpoints'
import CrudPage from '../../components/CrudPage'
import { ActiveFilter, ActiveTag, emptyToNull, upper } from '../../components/fields'
import RemoteSelect from '../../components/RemoteSelect'

export const branchLabel = (b) => `${b.code} · ${b.name}`

function WarehouseFields({ record, editing }) {
  return (
    <Row gutter={16}>
      <Col xs={24} sm={8}>
        <Form.Item name="code" label="Code" normalize={upper} rules={[{ required: true }]}>
          <Input placeholder="LSK-MAIN" maxLength={20} />
        </Form.Item>
      </Col>
      <Col xs={24} sm={16}>
        <Form.Item name="name" label="Name" rules={[{ required: true, min: 2 }]}>
          <Input placeholder="Lusaka main store" />
        </Form.Item>
      </Col>
      <Col span={24}>
        <Form.Item name="branch_id" label="Branch">
          <RemoteSelect
            queryKey={['branches']}
            fetcher={branchesApi.list}
            extraParams={{ is_active: true }}
            labelOf={branchLabel}
            selected={record?.branch}
            placeholder="None"
          />
        </Form.Item>
      </Col>
      <Col span={24}>
        <Form.Item name="address" label="Address">
          <Input.TextArea rows={2} />
        </Form.Item>
      </Col>
      {editing && (
        <Col span={24}>
          <Form.Item
            name="is_active"
            label="Active"
            valuePropName="checked"
            extra="A warehouse that still holds stock cannot be deactivated."
          >
            <Switch />
          </Form.Item>
        </Col>
      )}
    </Row>
  )
}

const warehouseFormValues = (w) => ({ ...w, branch_id: w.branch?.id || null })
const warehousePayload = (values, record) => {
  const body = emptyToNull(values, ['address', 'branch_id'])
  if (!record) delete body.is_active
  return body
}

export default function WarehousesPage() {
  const [active, setActive] = useState()
  return (
    <CrudPage
      title="Warehouses"
      subtitle="Places where stock is kept."
      entityLabel="Warehouse"
      queryKey={['warehouses']}
      api={warehousesApi}
      perms={{ create: 'company.update', update: 'company.update', delete: 'company.update' }}
      filters={{ is_active: active }}
      filterBar={<ActiveFilter value={active} onChange={setActive} />}
      searchPlaceholder="Search code or name"
      FormFields={WarehouseFields}
      toFormValues={warehouseFormValues}
      toPayload={warehousePayload}
      describe={(w) => `${w.code} ${w.name}`}
      columns={[
        { title: 'Code', dataIndex: 'code', key: 'code', sortField: 'code' },
        { title: 'Name', dataIndex: 'name', key: 'name', sortField: 'name' },
        { title: 'Branch', key: 'branch', render: (_, w) => (w.branch ? branchLabel(w.branch) : '—') },
        { title: 'Address', dataIndex: 'address', key: 'address', render: (v) => v || '—' },
        { title: 'Status', key: 'active', render: (_, w) => <ActiveTag active={w.is_active} /> },
      ]}
    />
  )
}
