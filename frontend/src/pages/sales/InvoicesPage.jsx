import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import {
  Alert,
  App,
  Button,
  Checkbox,
  DatePicker,
  Descriptions,
  Drawer,
  Dropdown,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Table,
  Tag,
  Typography,
} from 'antd'
import { MoreOutlined, PlusOutlined } from '@ant-design/icons'
import { customersApi, downloadFile, invoicesApi, paymentsApi } from '../../api/endpoints'
import { errorMessage } from '../../api/errors'
import { useAuth } from '../../auth/AuthContext'
import DataTable from '../../components/DataTable'
import PageHeader from '../../components/PageHeader'
import RemoteSelect from '../../components/RemoteSelect'
import StatusTag from '../../components/StatusTag'
import { toApiDate } from '../../utils/dates'
import { formatDate, formatMoney, formatQuantity, humanize } from '../../utils/format'
import SalesDocumentDrawer from './SalesDocumentDrawer'

export const PAYMENT_METHODS = ['CASH', 'BANK_TRANSFER', 'MOBILE_MONEY', 'CHEQUE', 'CARD'].map((m) => ({
  value: m,
  label: humanize(m),
}))

const invoiceLabel = (i) => i.invoice_number || 'Draft invoice'

function PaymentModal({ invoice, onClose }) {
  const [form] = Form.useForm()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: (v) =>
      invoicesApi.recordPayment(invoice.id, {
        amount: String(v.amount),
        method: v.method,
        payment_date: toApiDate(v.payment_date),
        reference: v.reference || null,
        notes: v.notes || null,
      }),
    onSuccess: (p) => {
      message.success(`Receipt ${p.receipt_number} recorded`)
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      queryClient.invalidateQueries({ queryKey: ['payments'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      onClose()
    },
    onError: (error) => message.error(errorMessage(error)),
  })
  return (
    <Modal
      title={invoice ? `Record payment: ${invoiceLabel(invoice)}` : 'Record payment'}
      open={Boolean(invoice)}
      onCancel={onClose}
      onOk={() => form.submit()}
      okText="Record payment"
      confirmLoading={mutation.isPending}
      destroyOnHidden
    >
      {invoice && (
        <>
          <Typography.Paragraph>
            {invoice.customer.name} owes <strong>{formatMoney(invoice.balance_due, invoice.currency)}</strong>.
          </Typography.Paragraph>
          <Form
            form={form}
            layout="vertical"
            onFinish={mutation.mutate}
            initialValues={{ amount: Number(invoice.balance_due), method: 'BANK_TRANSFER', payment_date: dayjs() }}
          >
            <Form.Item name="amount" label="Amount" rules={[{ required: true }]}>
              <InputNumber min={0.01} max={Number(invoice.balance_due)} precision={2} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="method" label="Method" rules={[{ required: true }]}>
              <Select options={PAYMENT_METHODS} />
            </Form.Item>
            <Form.Item name="payment_date" label="Date received" rules={[{ required: true }]}>
              <DatePicker style={{ width: '100%' }} format="DD/MM/YYYY" />
            </Form.Item>
            <Form.Item name="reference" label="Reference" extra="e.g. bank or mobile money transaction ID">
              <Input />
            </Form.Item>
          </Form>
        </>
      )}
    </Modal>
  )
}

function InvoiceDetail({ invoiceId, onClose }) {
  const { can } = useAuth()
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ['invoices', 'detail', invoiceId],
    queryFn: () => invoicesApi.get(invoiceId),
    enabled: Boolean(invoiceId),
  })
  const voidPayment = useMutation({
    mutationFn: ({ id, reason }) => paymentsApi.void(id, reason),
    onSuccess: () => {
      message.success('Payment voided')
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      queryClient.invalidateQueries({ queryKey: ['payments'] })
    },
    onError: (error) => message.error(errorMessage(error)),
  })
  const askVoid = (p) => {
    let reason = ''
    modal.confirm({
      title: `Void receipt ${p.receipt_number}?`,
      content: <Input.TextArea rows={2} placeholder="Reason (required)" onChange={(e) => { reason = e.target.value }} />,
      okText: 'Void payment',
      okButtonProps: { danger: true },
      onOk: () => {
        if (reason.trim().length < 3) {
          message.warning('Please give a reason')
          return Promise.reject(new Error('reason required'))
        }
        return voidPayment.mutateAsync({ id: p.id, reason: reason.trim() })
      },
    })
  }
  const inv = query.data
  return (
    <Drawer title={inv ? invoiceLabel(inv) : 'Invoice'} open={Boolean(invoiceId)} onClose={onClose} size={860} loading={query.isLoading}>
      {query.isError && <Alert type="error" showIcon title={errorMessage(query.error)} />}
      {inv && (
        <>
          <Descriptions bordered size="small" column={{ xs: 1, sm: 2 }} style={{ marginBottom: 16 }}>
            <Descriptions.Item label="Customer">{inv.customer.name}</Descriptions.Item>
            <Descriptions.Item label="Status"><StatusTag status={inv.status} /></Descriptions.Item>
            <Descriptions.Item label="Invoice date">{formatDate(inv.invoice_date)}</Descriptions.Item>
            <Descriptions.Item label="Due date">
              {formatDate(inv.due_date)} {inv.is_overdue && <Tag color="red">Overdue</Tag>}
            </Descriptions.Item>
            <Descriptions.Item label="Customer order no.">{inv.customer_reference || '—'}</Descriptions.Item>
            <Descriptions.Item label="Prices">{inv.prices_include_tax ? 'Include VAT' : 'Exclude VAT'}</Descriptions.Item>
          </Descriptions>
          <Table
            rowKey="id"
            size="small"
            pagination={false}
            dataSource={inv.lines}
            scroll={{ x: 'max-content' }}
            columns={[
              { title: 'Item', key: 'item', render: (_, l) => `${l.product.sku} · ${l.description}` },
              { title: 'Qty', dataIndex: 'quantity', key: 'qty', align: 'right', render: formatQuantity },
              { title: 'Price', dataIndex: 'unit_price', key: 'price', align: 'right', render: (v) => formatMoney(v, '') },
              { title: 'Disc %', dataIndex: 'discount_percent', key: 'disc', align: 'right', render: (v) => (Number(v) ? Number(v) : '') },
              { title: 'VAT', dataIndex: 'line_tax', key: 'tax', align: 'right', render: (v) => formatMoney(v, '') },
              { title: 'Total incl', dataIndex: 'line_total', key: 'total', align: 'right', render: (v) => formatMoney(v, '') },
            ]}
          />
          <Descriptions size="small" column={1} style={{ maxWidth: 360, marginLeft: 'auto', marginTop: 12 }}>
            <Descriptions.Item label="Total (excl VAT)">{formatMoney(inv.subtotal)}</Descriptions.Item>
            <Descriptions.Item label="VAT">{formatMoney(inv.tax_total)}</Descriptions.Item>
            <Descriptions.Item label={<strong>Total (incl VAT)</strong>}><strong>{formatMoney(inv.total)}</strong></Descriptions.Item>
            <Descriptions.Item label="Paid">{formatMoney(inv.amount_paid)}</Descriptions.Item>
            <Descriptions.Item label={<strong>Balance due</strong>}><strong>{formatMoney(inv.balance_due)}</strong></Descriptions.Item>
          </Descriptions>
          <Typography.Title level={5}>Payments</Typography.Title>
          <Table
            rowKey="id"
            size="small"
            pagination={false}
            dataSource={inv.payments}
            locale={{ emptyText: 'No payments yet' }}
            columns={[
              { title: 'Receipt', dataIndex: 'receipt_number', key: 'n' },
              { title: 'Date', dataIndex: 'payment_date', key: 'd', render: formatDate },
              { title: 'Method', dataIndex: 'method', key: 'm', render: humanize },
              { title: 'Reference', dataIndex: 'reference', key: 'r', render: (v) => v || '—' },
              { title: 'Amount', dataIndex: 'amount', key: 'a', align: 'right', render: (v) => formatMoney(v) },
              { title: 'Status', dataIndex: 'status', key: 's', render: (s) => <StatusTag status={s} /> },
              {
                title: '',
                key: 'x',
                render: (_, p) =>
                  p.status === 'POSTED' && can('finance.approve') ? (
                    <Button size="small" danger type="link" onClick={() => askVoid(p)}>
                      Void
                    </Button>
                  ) : null,
              },
            ]}
          />
        </>
      )}
    </Drawer>
  )
}

export default function InvoicesPage() {
  const { can } = useAuth()
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const [filters, setFilters] = useState({})
  const [drawer, setDrawer] = useState({ open: false, document: null })
  const [paying, setPaying] = useState(null)
  const [viewing, setViewing] = useState(null)
  const set = (patch) => setFilters((f) => ({ ...f, ...patch }))
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['invoices'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard'] })
  }

  const act = useMutation({
    mutationFn: ({ action, invoice, reason }) => {
      if (action === 'approve') return invoicesApi.approve(invoice.id)
      if (action === 'cancel') return invoicesApi.cancel(invoice.id, reason)
      return invoicesApi.remove(invoice.id)
    },
    onSuccess: (result, { action }) => {
      if (action === 'approve') message.success(`Invoice ${result.invoice_number} issued`)
      if (action === 'cancel') message.success('Invoice cancelled; goods returned to stock')
      if (action === 'delete') message.success('Draft deleted')
      refresh()
    },
    onError: (error) => message.error(errorMessage(error)),
  })

  const download = async (inv) => {
    try {
      await downloadFile(invoicesApi.pdfPath(inv.id), `${inv.invoice_number || 'draft-invoice'}.pdf`)
    } catch (error) {
      message.error(errorMessage(error, 'Could not download the PDF'))
    }
  }

  const actions = (inv) => {
    const items = [{ key: 'view', label: 'View details' }, { key: 'pdf', label: 'Download PDF' }]
    if (inv.status === 'DRAFT') {
      if (can('sales.update')) items.push({ key: 'edit', label: 'Edit' })
      if (can('sales.approve')) items.push({ key: 'approve', label: 'Approve and issue' })
      if (can('sales.delete')) items.push({ type: 'divider' }, { key: 'delete', label: 'Delete draft', danger: true })
    }
    if (['ISSUED', 'PARTIALLY_PAID'].includes(inv.status) && can('finance.create')) {
      items.push({ key: 'pay', label: 'Record payment' })
    }
    if (inv.status === 'ISSUED' && Number(inv.amount_paid) === 0 && can('sales.delete')) {
      items.push({ type: 'divider' }, { key: 'cancel', label: 'Cancel invoice', danger: true })
    }
    return items
  }

  const onAction = async (key, inv) => {
    if (key === 'view') return setViewing(inv.id)
    if (key === 'pdf') return download(inv)
    if (key === 'pay') return setPaying(inv)
    if (key === 'edit') {
      try {
        return setDrawer({ open: true, document: await invoicesApi.get(inv.id) })
      } catch (error) {
        return message.error(errorMessage(error))
      }
    }
    if (key === 'approve') {
      return modal.confirm({
        title: 'Approve and issue this invoice?',
        content: 'It gets its invoice number, the credit limit is checked, and goods leave the warehouse.',
        okText: 'Issue invoice',
        onOk: () => act.mutateAsync({ action: 'approve', invoice: inv }),
      })
    }
    if (key === 'delete') {
      return modal.confirm({
        title: 'Delete this draft invoice?',
        okText: 'Delete',
        okButtonProps: { danger: true },
        onOk: () => act.mutateAsync({ action: 'delete', invoice: inv }),
      })
    }
    if (key === 'cancel') {
      let reason = ''
      return modal.confirm({
        title: `Cancel ${inv.invoice_number}?`,
        content: <Input.TextArea rows={2} placeholder="Reason (required)" onChange={(e) => { reason = e.target.value }} />,
        okText: 'Cancel invoice',
        okButtonProps: { danger: true },
        cancelText: 'Keep it',
        onOk: () => {
          if (reason.trim().length < 3) {
            message.warning('Please give a reason')
            return Promise.reject(new Error('reason required'))
          }
          return act.mutateAsync({ action: 'cancel', invoice: inv, reason: reason.trim() })
        },
      })
    }
    return undefined
  }

  return (
    <>
      <PageHeader
        title="Invoices"
        subtitle="Draft, issue and collect payment on sales invoices."
        actions={
          can('sales.create') && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setDrawer({ open: true, document: null })}>
              New invoice
            </Button>
          )
        }
      />
      <DataTable
        queryKey={['invoices']}
        fetcher={invoicesApi.list}
        filters={filters}
        searchPlaceholder="Search number, customer or order no."
        toolbar={
          <>
            <Select
              allowClear
              placeholder="Any status"
              style={{ width: 160 }}
              value={filters.status}
              onChange={(status) => set({ status })}
              options={['DRAFT', 'ISSUED', 'PARTIALLY_PAID', 'PAID', 'CANCELLED'].map((s) => ({ value: s, label: humanize(s) }))}
            />
            <RemoteSelect
              queryKey={['customers']}
              fetcher={customersApi.list}
              labelOf={(c) => `${c.code} · ${c.name}`}
              placeholder="Any customer"
              style={{ width: 240 }}
              value={filters.customer_id}
              onChange={(customer_id) => set({ customer_id })}
            />
            <Checkbox checked={Boolean(filters.overdue)} onChange={(e) => set({ overdue: e.target.checked || undefined })}>
              Overdue only
            </Checkbox>
          </>
        }
        columns={[
          {
            title: 'Number',
            key: 'invoice_number',
            sortField: 'invoice_number',
            render: (_, i) => <Typography.Link onClick={() => setViewing(i.id)}>{invoiceLabel(i)}</Typography.Link>,
          },
          { title: 'Customer', key: 'customer', render: (_, i) => i.customer.name },
          { title: 'Date', dataIndex: 'invoice_date', key: 'invoice_date', sortField: 'invoice_date', render: formatDate },
          {
            title: 'Due',
            dataIndex: 'due_date',
            key: 'due_date',
            sortField: 'due_date',
            render: (v, i) => (
              <>
                {formatDate(v)} {i.is_overdue && <Tag color="red">Overdue</Tag>}
              </>
            ),
          },
          { title: 'Status', dataIndex: 'status', key: 'status', render: (s) => <StatusTag status={s} /> },
          { title: 'Total', dataIndex: 'total', key: 'total', sortField: 'total', align: 'right', render: (v, i) => formatMoney(v, i.currency) },
          { title: 'Balance', dataIndex: 'balance_due', key: 'balance', align: 'right', render: (v, i) => formatMoney(v, i.currency) },
          {
            title: '',
            key: 'actions',
            fixed: 'right',
            width: 56,
            render: (_, i) => (
              <Dropdown trigger={['click']} placement="bottomRight" menu={{ items: actions(i), onClick: ({ key }) => onAction(key, i) }}>
                <Button type="text" icon={<MoreOutlined />} aria-label={`Actions for ${invoiceLabel(i)}`} />
              </Dropdown>
            ),
          },
        ]}
      />
      <SalesDocumentDrawer
        kind="invoice"
        open={drawer.open}
        document={drawer.document}
        onClose={() => setDrawer({ open: false, document: null })}
      />
      <PaymentModal invoice={paying} onClose={() => setPaying(null)} />
      <InvoiceDetail invoiceId={viewing} onClose={() => setViewing(null)} />
    </>
  )
}
