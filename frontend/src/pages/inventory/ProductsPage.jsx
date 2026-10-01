import { useState } from 'react'
import {
  Col,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Switch,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import { categoriesApi, productsApi } from '../../api/endpoints'
import { useAuth } from '../../auth/AuthContext'
import CrudPage from '../../components/CrudPage'
import { ActiveFilter, ActiveTag, emptyToNull, upper } from '../../components/fields'
import PageHeader from '../../components/PageHeader'
import RemoteSelect from '../../components/RemoteSelect'
import { formatMoney, formatQuantity } from '../../utils/format'
import ProductStockDrawer from './ProductStockDrawer'

const categoryLabel = (c) => c.name

function ProductFields({ record, editing }) {
  const type = Form.useWatch('product_type')
  return (
    <>
      <Row gutter={16}>
        <Col xs={24} sm={8}>
          <Form.Item
            name="sku"
            label="Item code"
            normalize={upper}
            extra={editing ? null : 'Leave blank to number automatically (ITM-00001...)'}
            rules={[
              ...(editing ? [{ required: true, message: 'Enter an item code' }] : []),
              { pattern: /^[A-Z0-9\-_./]{1,40}$/, message: 'Letters, digits, - _ . or /' },
            ]}
          >
            <Input placeholder={editing ? 'CEM-50KG' : 'Automatic'} />
          </Form.Item>
        </Col>
        <Col xs={24} sm={16}>
          <Form.Item name="name" label="Name" rules={[{ required: true, min: 2 }]}>
            <Input placeholder="Cement 50kg bag" />
          </Form.Item>
        </Col>
        <Col xs={24} sm={8}>
          <Form.Item name="product_type" label="Type" rules={[{ required: true }]}>
            <Select
              disabled={editing}
              options={[
                { value: 'GOODS', label: 'Goods (stocked)' },
                { value: 'SERVICE', label: 'Service' },
              ]}
            />
          </Form.Item>
        </Col>
        <Col xs={24} sm={8}>
          <Form.Item name="category_id" label="Category">
            <RemoteSelect
              queryKey={['product-categories']}
              fetcher={categoriesApi.list}
              extraParams={{ is_active: true }}
              labelOf={categoryLabel}
              selected={record?.category}
              placeholder="None"
            />
          </Form.Item>
        </Col>
        <Col xs={24} sm={8}>
          <Form.Item name="unit" label="Unit" rules={[{ required: true }]}>
            <Input placeholder="pcs, bag, kg, litre" />
          </Form.Item>
        </Col>
        <Col xs={24} sm={8}>
          {editing ? (
            <Form.Item label="Average cost" extra="Updated automatically when goods are received.">
              <Typography.Text>{formatMoney(record.cost_price)}</Typography.Text>
            </Form.Item>
          ) : (
            <Form.Item name="cost_price" label="Cost price (ZMW)" extra="Starting cost; receipts update it.">
              <InputNumber min={0} precision={2} style={{ width: '100%' }} />
            </Form.Item>
          )}
        </Col>
        <Col xs={24} sm={8}>
          <Form.Item name="selling_price" label="Selling price (ZMW)" rules={[{ required: true }]}>
            <InputNumber min={0} precision={2} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col xs={24} sm={8}>
          <Form.Item name="tax_rate" label="VAT rate (%)" extra={editing ? null : 'Empty = default VAT'}>
            <InputNumber min={0} max={100} precision={2} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        {type !== 'SERVICE' && (
          <Col xs={24} sm={8}>
            <Form.Item
              name="reorder_level"
              label="Reorder level"
              extra="Alert when stock falls to this"
            >
              <InputNumber min={0} precision={3} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        )}
        <Col xs={24} sm={type !== 'SERVICE' ? 16 : 24}>
          <Form.Item name="barcode" label="Barcode">
            <Input />
          </Form.Item>
        </Col>
        <Col span={24}>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Col>
        {editing && (
          <Col span={24}>
            <Form.Item name="is_active" label="Active" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Col>
        )}
      </Row>
    </>
  )
}

const productFormValues = (p) => ({
  ...p,
  category_id: p.category?.id || null,
  selling_price: Number(p.selling_price),
  tax_rate: Number(p.tax_rate),
  reorder_level: Number(p.reorder_level),
})

const decimal = (v) => (v === null || v === undefined || v === '' ? null : String(v))

const productPayload = (values, record) => {
  const body = emptyToNull(values, ['sku', 'description', 'barcode', 'category_id'])
  body.selling_price = decimal(values.selling_price)
  body.tax_rate = decimal(values.tax_rate)
  body.reorder_level = decimal(values.reorder_level)
  if (record) {
    delete body.product_type
    delete body.cost_price
    if (body.tax_rate === null) delete body.tax_rate
    if (body.reorder_level === null) delete body.reorder_level
  } else {
    body.cost_price = decimal(values.cost_price) || '0'
    delete body.is_active
  }
  return body
}

function Products() {
  const { can } = useAuth()
  const [filters, setFilters] = useState({})
  const [stockOf, setStockOf] = useState(null)
  return (
    <>
      <CrudPage
        embedded
        entityLabel="Product"
        queryKey={['products']}
        api={productsApi}
        perms={{ create: 'products.create', update: 'products.update', delete: 'products.delete' }}
        filters={filters}
        filterBar={
          <>
            <Select
              allowClear
              placeholder="Goods or services"
              style={{ width: 170 }}
              value={filters.product_type}
              onChange={(product_type) => setFilters((f) => ({ ...f, product_type }))}
              options={[
                { value: 'GOODS', label: 'Goods' },
                { value: 'SERVICE', label: 'Services' },
              ]}
            />
            <RemoteSelect
              queryKey={['product-categories']}
              fetcher={categoriesApi.list}
              labelOf={categoryLabel}
              placeholder="Any category"
              style={{ width: 200 }}
              value={filters.category_id}
              onChange={(category_id) => setFilters((f) => ({ ...f, category_id }))}
            />
            <ActiveFilter
              value={filters.is_active}
              onChange={(is_active) => setFilters((f) => ({ ...f, is_active }))}
            />
          </>
        }
        searchPlaceholder="Search SKU, name or barcode"
        FormFields={ProductFields}
        toFormValues={productFormValues}
        toPayload={productPayload}
        initialValues={{ product_type: 'GOODS', unit: 'pcs', selling_price: 0, reorder_level: 0 }}
        formWidth={760}
        describe={(p) => `${p.sku} ${p.name}`}
        extraActions={(p) =>
          p.product_type === 'GOODS' && can('inventory.view')
            ? [{ key: 'stock', label: 'View stock', onClick: () => setStockOf(p.id) }]
            : []
        }
        columns={[
          { title: 'Item code', dataIndex: 'sku', key: 'sku', sortField: 'sku' },
          { title: 'Name', dataIndex: 'name', key: 'name', sortField: 'name' },
          {
            title: 'Type',
            dataIndex: 'product_type',
            key: 'type',
            render: (t) => (t === 'SERVICE' ? <Tag color="purple">Service</Tag> : <Tag>Goods</Tag>),
          },
          { title: 'Category', key: 'category', render: (_, p) => p.category?.name || '—' },
          { title: 'Unit', dataIndex: 'unit', key: 'unit' },
          {
            title: 'Cost',
            dataIndex: 'cost_price',
            key: 'cost',
            align: 'right',
            render: (v) => formatMoney(v),
          },
          {
            title: 'Price',
            dataIndex: 'selling_price',
            key: 'price',
            sortField: 'selling_price',
            align: 'right',
            render: (v) => formatMoney(v),
          },
          { title: 'VAT', dataIndex: 'tax_rate', key: 'vat', align: 'right', render: (v) => `${Number(v)}%` },
          {
            title: 'Reorder at',
            dataIndex: 'reorder_level',
            key: 'reorder',
            align: 'right',
            render: (v, p) => (p.product_type === 'SERVICE' ? '—' : formatQuantity(v)),
          },
          { title: 'Status', key: 'active', render: (_, p) => <ActiveTag active={p.is_active} /> },
        ]}
      />
      <ProductStockDrawer productId={stockOf} onClose={() => setStockOf(null)} />
    </>
  )
}

function CategoryFields({ editing }) {
  return (
    <>
      <Form.Item name="name" label="Name" rules={[{ required: true, min: 2 }]}>
        <Input placeholder="Building materials" />
      </Form.Item>
      <Form.Item name="description" label="Description">
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

const categoryPayload = (values, record) => {
  const body = emptyToNull(values, ['description'])
  if (!record) delete body.is_active
  return body
}

function Categories() {
  const [active, setActive] = useState()
  return (
    <CrudPage
      embedded
      entityLabel="Category"
      queryKey={['product-categories']}
      api={categoriesApi}
      perms={{ create: 'products.create', update: 'products.update', delete: 'products.delete' }}
      filters={{ is_active: active }}
      filterBar={<ActiveFilter value={active} onChange={setActive} />}
      searchPlaceholder="Search categories"
      FormFields={CategoryFields}
      toPayload={categoryPayload}
      columns={[
        { title: 'Name', dataIndex: 'name', key: 'name', sortField: 'name' },
        { title: 'Description', dataIndex: 'description', key: 'description', render: (v) => v || '—' },
        { title: 'Status', key: 'active', render: (_, c) => <ActiveTag active={c.is_active} /> },
      ]}
    />
  )
}

export default function ProductsPage() {
  return (
    <>
      <PageHeader title="Products" subtitle="Goods you stock and services you sell." />
      <Tabs
        destroyOnHidden
        items={[
          { key: 'products', label: 'Products', children: <Products /> },
          { key: 'categories', label: 'Categories', children: <Categories /> },
        ]}
      />
    </>
  )
}
