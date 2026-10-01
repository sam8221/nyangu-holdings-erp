import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { App, Button, DatePicker, Input, Select } from 'antd'
import { paymentsApi } from '../../api/endpoints'
import { errorMessage } from '../../api/errors'
import { useAuth } from '../../auth/AuthContext'
import DataTable from '../../components/DataTable'
import PageHeader from '../../components/PageHeader'
import StatusTag from '../../components/StatusTag'
import { toApiDate } from '../../utils/dates'
import { formatDate, formatMoney, humanize } from '../../utils/format'
import { PAYMENT_METHODS } from './InvoicesPage'

export default function PaymentsPage() {
  const { can } = useAuth()
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const [filters, setFilters] = useState({})
  const set = (patch) => setFilters((f) => ({ ...f, ...patch }))

  const voidPayment = useMutation({
    mutationFn: ({ id, reason }) => paymentsApi.void(id, reason),
    onSuccess: () => {
      message.success('Payment voided; the invoice balance is open again')
      queryClient.invalidateQueries({ queryKey: ['payments'] })
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
    },
    onError: (error) => message.error(errorMessage(error)),
  })

  const askVoid = (p) => {
    let reason = ''
    modal.confirm({
      title: `Void receipt ${p.receipt_number}?`,
      content: (
        <Input.TextArea rows={2} placeholder="Reason (required)" onChange={(e) => { reason = e.target.value }} />
      ),
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

  return (
    <>
      <PageHeader title="Payments" subtitle="Money received from customers against invoices." />
      <DataTable
        queryKey={['payments']}
        fetcher={paymentsApi.list}
        filters={filters}
        searchPlaceholder="Search receipt, reference or customer"
        toolbar={
          <>
            <Select
              allowClear
              placeholder="Any method"
              style={{ width: 170 }}
              value={filters.method}
              onChange={(method) => set({ method })}
              options={PAYMENT_METHODS}
            />
            <Select
              allowClear
              placeholder="Any status"
              style={{ width: 140 }}
              value={filters.status}
              onChange={(status) => set({ status })}
              options={[{ value: 'POSTED', label: 'Posted' }, { value: 'VOIDED', label: 'Voided' }]}
            />
            <DatePicker.RangePicker
              format="DD/MM/YYYY"
              onChange={(r) => set({ date_from: toApiDate(r?.[0]) || undefined, date_to: toApiDate(r?.[1]) || undefined })}
            />
          </>
        }
        columns={[
          { title: 'Receipt', dataIndex: 'receipt_number', key: 'receipt_number', sortField: 'receipt_number' },
          { title: 'Date', dataIndex: 'payment_date', key: 'payment_date', sortField: 'payment_date', render: formatDate },
          { title: 'Customer', key: 'customer', render: (_, p) => p.customer.name },
          { title: 'Invoice', dataIndex: 'invoice_number', key: 'invoice', render: (v) => v || '—' },
          { title: 'Method', dataIndex: 'method', key: 'method', render: humanize },
          { title: 'Reference', dataIndex: 'reference', key: 'reference', render: (v) => v || '—' },
          { title: 'Amount', dataIndex: 'amount', key: 'amount', sortField: 'amount', align: 'right', render: (v) => formatMoney(v) },
          { title: 'Status', dataIndex: 'status', key: 'status', render: (s) => <StatusTag status={s} /> },
          {
            title: '',
            key: 'actions',
            render: (_, p) =>
              p.status === 'POSTED' && can('finance.approve') ? (
                <Button size="small" type="link" danger onClick={() => askVoid(p)}>
                  Void
                </Button>
              ) : null,
          },
        ]}
      />
    </>
  )
}
