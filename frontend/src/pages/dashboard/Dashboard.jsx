import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import dayjs from 'dayjs'
import { Alert, Button, Card, Col, Empty, List, Row, Skeleton, Statistic, Tag } from 'antd'
import { CheckCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import { dashboardApi } from '../../api/endpoints'
import { errorMessage } from '../../api/errors'
import { useAuth } from '../../auth/AuthContext'
import MiniBarChart from '../../components/MiniBarChart'
import PageHeader from '../../components/PageHeader'
import { colors } from '../../theme'
import { formatDate, formatMoney } from '../../utils/format'

const APPROVALS = {
  sales_invoices: { label: 'Draft invoices to issue', to: '/sales/invoices' },
  purchase_orders: { label: 'Purchase orders to approve', to: '/procurement/purchase-orders' },
  expenses: { label: 'Expenses to approve', to: '/finance/expenses' },
  supplier_bills: { label: 'Supplier bills to approve', to: '/finance/bills' },
  leave_requests: { label: 'Leave requests to decide', to: '/leave' },
}

function Tile({ title, value, money, currency, danger, to }) {
  const content = (
    <Card
      size="small"
      hoverable={Boolean(to)}
      style={{ height: '100%', borderTop: `3px solid ${danger ? '#e53935' : colors.primary}` }}
    >
      <Statistic
        title={title}
        value={money ? formatMoney(value, currency) : value}
        styles={{ content: { fontSize: 22, color: danger ? '#c62828' : colors.text } }}
      />
    </Card>
  )
  return to ? <Link to={to}>{content}</Link> : content
}

function Section({ title, children }) {
  return (
    <Card title={title} style={{ marginBottom: 16 }} styles={{ header: { color: colors.primaryDark } }}>
      <Row gutter={[16, 16]}>{children}</Row>
    </Card>
  )
}

const col = { xs: 24, sm: 12, lg: 6 }

export default function Dashboard() {
  const { user } = useAuth()
  const query = useQuery({ queryKey: ['dashboard'], queryFn: dashboardApi.summary })
  const data = query.data
  const currency = data?.currency || 'ZMW'
  const approvals = Object.entries(data?.pending_approvals || {})
  const firstName = user.full_name.split(' ')[0]

  return (
    <>
      <PageHeader
        title={`Welcome, ${firstName}`}
        subtitle={data ? `Figures as of ${formatDate(data.as_of)}` : ' '}
        actions={
          <Button icon={<ReloadOutlined />} onClick={() => query.refetch()} loading={query.isFetching}>
            Refresh
          </Button>
        }
      />
      {query.isError && (
        <Alert type="error" showIcon title={errorMessage(query.error)} style={{ marginBottom: 16 }} />
      )}
      {query.isLoading && <Skeleton active paragraph={{ rows: 8 }} />}
      {data && (
        <Row gutter={16}>
          <Col xs={24} xl={16}>
            {data.sales && (
              <Section title="Sales">
                <Col {...col}>
                  <Tile title="Invoiced this month" value={data.sales.invoiced_this_month} money currency={currency} to="/sales/invoices" />
                </Col>
                <Col {...col}>
                  <Tile title="Collected this month" value={data.sales.collected_this_month} money currency={currency} to="/sales/payments" />
                </Col>
                <Col {...col}>
                  <Tile title="Invoices this month" value={data.sales.invoices_this_month} to="/sales/invoices" />
                </Col>
                <Col {...col}>
                  <Tile
                    title={`Overdue (${data.sales.overdue_invoices})`}
                    value={data.sales.overdue_amount}
                    money
                    currency={currency}
                    danger={data.sales.overdue_invoices > 0}
                    to="/finance/receivables"
                  />
                </Col>
                <Col span={24}>
                  <div style={{ fontWeight: 600, marginBottom: 8 }}>Net sales, last 6 months</div>
                  <MiniBarChart
                    currency={currency}
                    data={data.sales.monthly_net_sales.map((m) => ({
                      label: dayjs(`${m.month}-01`).format('MMM'),
                      value: m.net_sales,
                    }))}
                  />
                </Col>
              </Section>
            )}
            {data.finance && (
              <Section title="Finance">
                <Col {...col}>
                  <Tile title="Receivables" value={data.finance.receivables_outstanding} money currency={currency} to="/finance/receivables" />
                </Col>
                <Col {...col}>
                  <Tile title="Payables" value={data.finance.payables_outstanding} money currency={currency} to="/finance/payables" />
                </Col>
                <Col {...col}>
                  <Tile title="Expenses this month" value={data.finance.expenses_this_month} money currency={currency} to="/finance/expenses" />
                </Col>
                <Col {...col}>
                  <Tile title="Bills due in 7 days" value={data.finance.bills_due_in_7_days} to="/finance/bills" />
                </Col>
              </Section>
            )}
            {(data.inventory || data.procurement) && (
              <Section title="Stock and purchasing">
                {data.inventory && (
                  <>
                    <Col {...col}>
                      <Tile title="Stock value" value={data.inventory.stock_value} money currency={currency} to="/inventory/stock" />
                    </Col>
                    <Col {...col}>
                      <Tile
                        title="Low-stock products"
                        value={data.inventory.low_stock_products}
                        danger={data.inventory.low_stock_products > 0}
                        to="/inventory/stock"
                      />
                    </Col>
                  </>
                )}
                {data.procurement && (
                  <>
                    <Col {...col}>
                      <Tile title="Open purchase orders" value={data.procurement.open_purchase_orders} to="/procurement/purchase-orders" />
                    </Col>
                    <Col {...col}>
                      <Tile title="Open order value" value={data.procurement.open_order_value} money currency={currency} />
                    </Col>
                  </>
                )}
              </Section>
            )}
            {(data.hr || data.assets) && (
              <Section title="People and assets">
                {data.hr && (
                  <>
                    <Col {...col}>
                      <Tile title="Headcount" value={data.hr.headcount} to="/employees" />
                    </Col>
                    <Col {...col}>
                      <Tile title="On leave today" value={data.hr.on_leave_today} to="/leave" />
                    </Col>
                  </>
                )}
                {data.assets && (
                  <>
                    <Col {...col}>
                      <Tile title="Active assets" value={data.assets.active_assets} to="/assets" />
                    </Col>
                    <Col {...col}>
                      <Tile title="Asset book value" value={data.assets.total_book_value} money currency={currency} to="/assets" />
                    </Col>
                  </>
                )}
              </Section>
            )}
          </Col>
          <Col xs={24} xl={8}>
            <Card title="Waiting for you" style={{ marginBottom: 16 }} styles={{ header: { color: colors.primaryDark } }}>
              {approvals.length === 0 ? (
                <Empty description="Nothing to approve" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                <List
                  dataSource={approvals}
                  renderItem={([key, count]) => (
                    <List.Item
                      actions={[
                        <Link key="open" to={APPROVALS[key]?.to || '/'}>
                          Open
                        </Link>,
                      ]}
                    >
                      <List.Item.Meta
                        avatar={
                          count > 0 ? (
                            <Tag color="blue" style={{ minWidth: 32, textAlign: 'center' }}>
                              {count}
                            </Tag>
                          ) : (
                            <CheckCircleOutlined style={{ color: '#43a047', fontSize: 18 }} />
                          )
                        }
                        title={APPROVALS[key]?.label || key}
                      />
                    </List.Item>
                  )}
                />
              )}
            </Card>
            <Card size="small">
              <Statistic title="Unread notifications" value={data.unread_notifications} />
            </Card>
          </Col>
        </Row>
      )}
    </>
  )
}
