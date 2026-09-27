import { useState } from 'react'
import { Button, Checkbox, Tabs, Tag, Typography } from 'antd'
import { SwapOutlined, ToolOutlined } from '@ant-design/icons'
import { categoriesApi, inventoryApi, warehousesApi } from '../../api/endpoints'
import { useAuth } from '../../auth/AuthContext'
import DataTable from '../../components/DataTable'
import PageHeader from '../../components/PageHeader'
import RemoteSelect from '../../components/RemoteSelect'
import { formatDateTime, formatQuantity } from '../../utils/format'
import ProductStockDrawer from './ProductStockDrawer'
import StockOperationModal, { warehouseLabel } from './StockOperationModal'

function Levels({ onOpenProduct }) {
  const [filters, setFilters] = useState({ include_zero: false })
  return (
    <DataTable
      queryKey={['inventory', 'levels']}
      fetcher={inventoryApi.stockLevels}
      filters={filters}
      searchPlaceholder="Search SKU or name"
      toolbar={
        <>
          <RemoteSelect
            queryKey={['warehouses']}
            fetcher={warehousesApi.list}
            labelOf={warehouseLabel}
            placeholder="All warehouses"
            style={{ width: 220 }}
            value={filters.warehouse_id}
            onChange={(warehouse_id) => setFilters((f) => ({ ...f, warehouse_id }))}
          />
          <RemoteSelect
            queryKey={['product-categories']}
            fetcher={categoriesApi.list}
            labelOf={(c) => c.name}
            placeholder="Any category"
            style={{ width: 200 }}
            value={filters.category_id}
            onChange={(category_id) => setFilters((f) => ({ ...f, category_id }))}
          />
          <Checkbox
            checked={filters.include_zero}
            onChange={(e) => setFilters((f) => ({ ...f, include_zero: e.target.checked }))}
          >
            Show zero stock
          </Checkbox>
        </>
      }
      columns={[
        {
          title: 'SKU',
          key: 'sku',
          sortField: 'sku',
          render: (_, l) => (
            <Typography.Link onClick={() => onOpenProduct(l.product.id)}>{l.product.sku}</Typography.Link>
          ),
        },
        { title: 'Product', key: 'name', sortField: 'name', render: (_, l) => l.product.name },
        { title: 'Warehouse', key: 'warehouse', render: (_, l) => warehouseLabel(l.warehouse) },
        {
          title: 'On hand',
          key: 'quantity',
          sortField: 'quantity',
          align: 'right',
          render: (_, l) => `${formatQuantity(l.quantity)} ${l.product.unit}`,
        },
        {
          title: 'Last change',
          dataIndex: 'updated_at',
          key: 'updated_at',
          sortField: 'updated_at',
          render: formatDateTime,
        },
      ]}
    />
  )
}

function LowStock({ onOpenProduct }) {
  return (
    <DataTable
      queryKey={['inventory', 'low']}
      fetcher={inventoryApi.lowStock}
      rowKey="product_id"
      searchPlaceholder="Search SKU or name"
      columns={[
        {
          title: 'SKU',
          key: 'sku',
          render: (_, p) => (
            <Typography.Link onClick={() => onOpenProduct(p.product_id)}>{p.sku}</Typography.Link>
          ),
        },
        { title: 'Product', dataIndex: 'name', key: 'name' },
        {
          title: 'On hand',
          key: 'on_hand',
          align: 'right',
          render: (_, p) => (
            <Tag color="red">
              {formatQuantity(p.on_hand)} {p.unit}
            </Tag>
          ),
        },
        {
          title: 'Reorder level',
          key: 'reorder',
          align: 'right',
          render: (_, p) => `${formatQuantity(p.reorder_level)} ${p.unit}`,
        },
        {
          title: 'Short by',
          key: 'shortfall',
          align: 'right',
          render: (_, p) => `${formatQuantity(p.shortfall)} ${p.unit}`,
        },
      ]}
    />
  )
}

export default function StockPage() {
  const { can } = useAuth()
  const [operation, setOperation] = useState(null)
  const [productId, setProductId] = useState(null)
  return (
    <>
      <PageHeader
        title="Stock levels"
        subtitle="What is on hand in each warehouse."
        actions={
          <>
            {can('inventory.transfer') && (
              <Button icon={<SwapOutlined />} onClick={() => setOperation('transfer')}>
                Transfer stock
              </Button>
            )}
            {can('inventory.adjust') && (
              <Button type="primary" icon={<ToolOutlined />} onClick={() => setOperation('adjust')}>
                Adjust stock
              </Button>
            )}
          </>
        }
      />
      <Tabs
        destroyOnHidden
        items={[
          { key: 'levels', label: 'By warehouse', children: <Levels onOpenProduct={setProductId} /> },
          { key: 'low', label: 'Low stock', children: <LowStock onOpenProduct={setProductId} /> },
        ]}
      />
      <StockOperationModal mode={operation} open={Boolean(operation)} onClose={() => setOperation(null)} />
      <ProductStockDrawer productId={productId} onClose={() => setProductId(null)} />
    </>
  )
}
