import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { App, Button, DatePicker, Dropdown, Form, Modal, Select, Tag, Typography } from 'antd'
import { MoreOutlined, PlusOutlined } from '@ant-design/icons'
import { customersApi, downloadFile, quotationsApi, warehousesApi } from '../../api/endpoints'
import { errorMessage } from '../../api/errors'
import { useAuth } from '../../auth/AuthContext'
import DataTable from '../../components/DataTable'
import PageHeader from '../../components/PageHeader'
import RemoteSelect from '../../components/RemoteSelect'
import StatusTag from '../../components/StatusTag'
import { toApiDate } from '../../utils/dates'
import { formatDate, formatMoney, humanize } from '../../utils/format'
import SalesDocumentDrawer from './SalesDocumentDrawer'

const STATUSES = ['DRAFT', 'SENT', 'ACCEPTED', 'DECLINED', 'CONVERTED']
// Mirrors the server's allowed status changes.
const NEXT = {
  DRAFT: ['SENT', 'ACCEPTED', 'DECLINED'],
  SENT: ['ACCEPTED', 'DECLINED'],
  ACCEPTED: ['SENT', 'DECLINED'],
  DECLINED: ['SENT'],
  CONVERTED: [],
}
const STATUS_ACTION = { SENT: 'Mark as sent', ACCEPTED: 'Mark as accepted', DECLINED: 'Mark as declined' }

function ConvertModal({ quotation, onClose }) {
  const [form] = Form.useForm()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: (v) => quotationsApi.convert(quotation.id, { warehouse_id: v.warehouse_id || null }),
    onSuccess: () => {
      message.success(`Draft invoice created from ${quotation.quote_number}`)
      queryClient.invalidateQueries({ queryKey: ['quotations'] })
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      onClose()
      navigate('/sales/invoices')
    },
    onError: (error) => message.error(errorMessage(error)),
  })
  return (
    <Modal
      title={quotation ? `Convert ${quotation.quote_number} to an invoice` : 'Convert'}
      open={Boolean(quotation)}
      onCancel={onClose}
      onOk={() => form.submit()}
      okText="Create draft invoice"
      confirmLoading={mutation.isPending}
      destroyOnHidden
    >
      <Typography.Paragraph type="secondary">
        A draft invoice is created with the same customer, items and prices. Review it and issue it
        from the Invoices page.
      </Typography.Paragraph>
      <Form form={form} layout="vertical" onFinish={mutation.mutate}>
        <Form.Item name="warehouse_id" label="Issue goods from" extra="You can also choose this later on the invoice.">
          <RemoteSelect
            queryKey={['warehouses']}
            fetcher={warehousesApi.list}
            extraParams={{ is_active: true }}
            labelOf={(w) => `${w.code} · ${w.name}`}
            placeholder="Warehouse"
          />
        </Form.Item>
      </Form>
    </Modal>
  )
}

export default function QuotationsPage() {
  const { can } = useAuth()
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const [filters, setFilters] = useState({})
  const [drawer, setDrawer] = useState({ open: false, document: null })
  const [converting, setConverting] = useState(null)
  const set = (patch) => setFilters((f) => ({ ...f, ...patch }))
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['quotations'] })

  const statusMutation = useMutation({
    mutationFn: ({ q, status }) => quotationsApi.setStatus(q.id, status),
    onSuccess: (q) => {
      message.success(`${q.quote_number} is now ${humanize(q.status).toLowerCase()}`)
      refresh()
    },
    onError: (error) => message.error(errorMessage(error)),
  })
  const remove = useMutation({
    mutationFn: (q) => quotationsApi.remove(q.id),
    onSuccess: () => {
      message.success('Quotation deleted')
      refresh()
    },
    onError: (error) => message.error(errorMessage(error)),
  })

  const openFull = async (q, then) => {
    try {
      then(await quotationsApi.get(q.id))
    } catch (error) {
      message.error(errorMessage(error))
    }
  }

  const download = async (q) => {
    try {
      await downloadFile(quotationsApi.pdfPath(q.id), `${q.quote_number}.pdf`)
    } catch (error) {
      message.error(errorMessage(error, 'Could not download the PDF'))
    }
  }

  const actions = (q) => {
    const items = [{ key: 'pdf', label: 'Download PDF' }]
    if (can('sales.update') && ['DRAFT', 'SENT'].includes(q.status)) items.unshift({ key: 'edit', label: 'Edit' })
    if (can('sales.update')) {
      for (const next of NEXT[q.status]) items.push({ key: `status:${next}`, label: STATUS_ACTION[next] })
    }
    if (can('sales.create') && !['CONVERTED', 'DECLINED'].includes(q.status)) {
      items.push({ type: 'divider' }, { key: 'convert', label: 'Convert to invoice' })
    }
    if (can('sales.delete') && q.status === 'DRAFT') {
      items.push({ type: 'divider' }, { key: 'delete', label: 'Delete', danger: true })
    }
    return items
  }

  const onAction = (key, q) => {
    if (key === 'edit') return openFull(q, (full) => setDrawer({ open: true, document: full }))
    if (key === 'pdf') return download(q)
    if (key === 'convert') return setConverting(q)
    if (key.startsWith('status:')) return statusMutation.mutate({ q, status: key.split(':')[1] })
    if (key === 'delete') {
      return modal.confirm({
        title: `Delete ${q.quote_number}?`,
        okText: 'Delete',
        okButtonProps: { danger: true },
        onOk: () => remove.mutateAsync(q),
      })
    }
    return undefined
  }

  return (
    <>
      <PageHeader
        title="Quotations"
        subtitle="Price quotes for customers. Accepted quotes can be turned into invoices."
        actions={
          can('sales.create') && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setDrawer({ open: true, document: null })}>
              New quotation
            </Button>
          )
        }
      />
      <DataTable
        queryKey={['quotations']}
        fetcher={quotationsApi.list}
        filters={filters}
        searchPlaceholder="Search number, customer or order no."
        toolbar={
          <>
            <Select
              allowClear
              placeholder="Any status"
              style={{ width: 150 }}
              value={filters.status}
              onChange={(status) => set({ status })}
              options={STATUSES.map((s) => ({ value: s, label: humanize(s) }))}
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
            <DatePicker.RangePicker
              format="DD/MM/YYYY"
              onChange={(r) => set({ date_from: toApiDate(r?.[0]) || undefined, date_to: toApiDate(r?.[1]) || undefined })}
            />
          </>
        }
        columns={[
          { title: 'Number', dataIndex: 'quote_number', key: 'quote_number', sortField: 'quote_number' },
          {
            title: 'Customer',
            key: 'customer',
            render: (_, q) => (
              <div>
                {q.customer.name}
                {q.customer_reference && (
                  <div className="muted" style={{ fontSize: 12 }}>
                    Order {q.customer_reference}
                  </div>
                )}
              </div>
            ),
          },
          { title: 'Date', dataIndex: 'quote_date', key: 'quote_date', sortField: 'quote_date', render: formatDate },
          {
            title: 'Valid until',
            dataIndex: 'valid_until',
            key: 'valid_until',
            sortField: 'valid_until',
            render: (v, q) => (
              <>
                {formatDate(v)} {q.is_expired && <Tag color="red">Expired</Tag>}
              </>
            ),
          },
          { title: 'Status', dataIndex: 'status', key: 'status', render: (s) => <StatusTag status={s} /> },
          {
            title: 'Total (incl VAT)',
            dataIndex: 'total',
            key: 'total',
            sortField: 'total',
            align: 'right',
            render: (v, q) => formatMoney(v, q.currency),
          },
          {
            title: '',
            key: 'actions',
            fixed: 'right',
            width: 56,
            render: (_, q) => (
              <Dropdown trigger={['click']} placement="bottomRight" menu={{ items: actions(q), onClick: ({ key }) => onAction(key, q) }}>
                <Button type="text" icon={<MoreOutlined />} aria-label={`Actions for ${q.quote_number}`} />
              </Dropdown>
            ),
          },
        ]}
      />
      <SalesDocumentDrawer
        kind="quotation"
        open={drawer.open}
        document={drawer.document}
        onClose={() => setDrawer({ open: false, document: null })}
      />
      <ConvertModal quotation={converting} onClose={() => setConverting(null)} />
    </>
  )
}
