import { useQuery } from '@tanstack/react-query'
import { Alert, Descriptions, Drawer, Table, Tag } from 'antd'
import { inventoryApi } from '../../api/endpoints'
import { errorMessage } from '../../api/errors'
import { formatMoney, formatQuantity } from '../../utils/format'

/** Stock of one product across warehouses. */
export default function ProductStockDrawer({ productId, onClose }) {
  const query = useQuery({
    queryKey: ['inventory', 'product', productId],
    queryFn: () => inventoryApi.productStock(productId),
    enabled: Boolean(productId),
  })
  const data = query.data

  return (
    <Drawer
      title={data ? `${data.sku} · ${data.name}` : 'Stock'}
      open={Boolean(productId)}
      onClose={onClose}
      size={520}
      loading={query.isLoading}
    >
      {query.isError && <Alert type="error" showIcon title={errorMessage(query.error)} />}
      {data && (
        <>
          <Descriptions column={1} size="small" bordered style={{ marginBottom: 16 }}>
            <Descriptions.Item label="Total on hand">
              {formatQuantity(data.total_quantity)} {data.unit}{' '}
              {data.is_low && <Tag color="red">Low stock</Tag>}
            </Descriptions.Item>
            <Descriptions.Item label="Reorder level">
              {formatQuantity(data.reorder_level)} {data.unit}
            </Descriptions.Item>
            <Descriptions.Item label="Stock value (average cost)">
              {formatMoney(data.stock_value)}
            </Descriptions.Item>
          </Descriptions>
          <Table
            rowKey="warehouse_id"
            size="small"
            pagination={false}
            dataSource={data.warehouses}
            locale={{ emptyText: 'No stock recorded yet' }}
            columns={[
              { title: 'Warehouse', key: 'wh', render: (_, w) => `${w.code} · ${w.name}` },
              {
                title: 'Quantity',
                dataIndex: 'quantity',
                key: 'quantity',
                align: 'right',
                render: (q) => `${formatQuantity(q)} ${data.unit}`,
              },
            ]}
          />
        </>
      )}
    </Drawer>
  )
}
