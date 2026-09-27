import { useState } from 'react'
import { DatePicker, Input, Select, Tag } from 'antd'
import { inventoryApi, productsApi, warehousesApi } from '../../api/endpoints'
import DataTable from '../../components/DataTable'
import PageHeader from '../../components/PageHeader'
import RemoteSelect from '../../components/RemoteSelect'
import { toApiDate } from '../../utils/dates'
import { formatDateTime, formatMoney, formatQuantity, humanize } from '../../utils/format'
import { productLabel, warehouseLabel } from './StockOperationModal'

const TYPES = ['RECEIPT', 'SALE', 'SALE_REVERSAL', 'ADJUSTMENT', 'TRANSFER_OUT', 'TRANSFER_IN']

export default function MovementsPage() {
  const [filters, setFilters] = useState({})
  const set = (patch) => setFilters((f) => ({ ...f, ...patch }))
  return (
    <>
      <PageHeader title="Stock movements" subtitle="Every change to stock, with the balance after it." />
      <DataTable
        queryKey={['inventory', 'movements']}
        fetcher={inventoryApi.movements}
        filters={filters}
        searchable={false}
        toolbar={
          <>
            <RemoteSelect
              queryKey={['products']}
              fetcher={productsApi.list}
              extraParams={{ product_type: 'GOODS' }}
              labelOf={productLabel}
              placeholder="Any product"
              style={{ width: 240 }}
              value={filters.product_id}
              onChange={(product_id) => set({ product_id })}
            />
            <RemoteSelect
              queryKey={['warehouses']}
              fetcher={warehousesApi.list}
              labelOf={warehouseLabel}
              placeholder="Any warehouse"
              style={{ width: 200 }}
              value={filters.warehouse_id}
              onChange={(warehouse_id) => set({ warehouse_id })}
            />
            <Select
              allowClear
              placeholder="Any type"
              style={{ width: 170 }}
              value={filters.movement_type}
              onChange={(movement_type) => set({ movement_type })}
              options={TYPES.map((t) => ({ value: t, label: humanize(t) }))}
            />
            <Input.Search
              allowClear
              placeholder="Reference, e.g. INV-2026-00001"
              style={{ width: 240 }}
              onSearch={(v) => set({ reference_number: v.trim() || undefined })}
            />
            <DatePicker.RangePicker
              onChange={(range) =>
                set({ date_from: toApiDate(range?.[0]) || undefined, date_to: toApiDate(range?.[1]) || undefined })
              }
            />
          </>
        }
        columns={[
          {
            title: 'When',
            dataIndex: 'created_at',
            key: 'created_at',
            sortField: 'created_at',
            render: formatDateTime,
          },
          { title: 'Product', key: 'product', render: (_, m) => productLabel(m.product) },
          { title: 'Warehouse', key: 'warehouse', render: (_, m) => m.warehouse.code },
          {
            title: 'Type',
            dataIndex: 'movement_type',
            key: 'type',
            render: (t) => <Tag color={t.endsWith('IN') || t === 'RECEIPT' || t === 'SALE_REVERSAL' ? 'green' : 'blue'}>{humanize(t)}</Tag>,
          },
          {
            title: 'Quantity',
            dataIndex: 'quantity',
            key: 'quantity',
            sortField: 'quantity',
            align: 'right',
            render: (q) => (
              <span style={{ color: Number(q) < 0 ? '#c62828' : '#2e7d32' }}>
                {Number(q) > 0 ? '+' : ''}
                {formatQuantity(q)}
              </span>
            ),
          },
          {
            title: 'Balance after',
            dataIndex: 'balance_after',
            key: 'balance',
            align: 'right',
            render: formatQuantity,
          },
          { title: 'Unit cost', dataIndex: 'unit_cost', key: 'cost', align: 'right', render: (v) => formatMoney(v) },
          { title: 'Reference', dataIndex: 'reference_number', key: 'ref', render: (v) => v || '—' },
          { title: 'Notes', dataIndex: 'notes', key: 'notes', render: (v) => v || '—' },
        ]}
      />
    </>
  )
}
