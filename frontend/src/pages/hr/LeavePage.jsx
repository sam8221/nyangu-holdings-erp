import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import {
  Alert,
  App,
  Button,
  DatePicker,
  Dropdown,
  Form,
  Input,
  Modal,
  Select,
  Typography,
} from 'antd'
import { MoreOutlined, PlusOutlined } from '@ant-design/icons'
import { employeesApi, leaveApi } from '../../api/endpoints'
import { applyFieldErrors, errorMessage } from '../../api/errors'
import { useAuth } from '../../auth/AuthContext'
import DataTable from '../../components/DataTable'
import PageHeader from '../../components/PageHeader'
import RemoteSelect from '../../components/RemoteSelect'
import StatusTag from '../../components/StatusTag'
import { toApiDate } from '../../utils/dates'
import { formatDate, formatDateTime, humanize } from '../../utils/format'
import { employeeLabel } from './EmployeeFormDrawer'

export const LEAVE_TYPES = ['ANNUAL', 'SICK', 'MATERNITY', 'PATERNITY', 'COMPASSIONATE', 'STUDY', 'UNPAID'].map(
  (t) => ({ value: t, label: humanize(t) }),
)

/** Monday to Friday between two dates, inclusive (same rule as the server). */
export function workingDays(start, end) {
  if (!start || !end || end.isBefore(start, 'day')) return 0
  let days = 0
  for (let d = start.startOf('day'); !d.isAfter(end, 'day'); d = d.add(1, 'day')) {
    if (d.day() !== 0 && d.day() !== 6) days += 1
  }
  return days
}

function RequestLeaveModal({ open, onClose }) {
  const [form] = Form.useForm()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const employeeId = Form.useWatch('employee_id', form)
  const leaveType = Form.useWatch('leave_type', form)
  const range = Form.useWatch('range', form)
  const days = workingDays(range?.[0], range?.[1])
  const year = range?.[0]?.year() || dayjs().year()

  const balance = useQuery({
    queryKey: ['leave-balance', employeeId, year],
    queryFn: () => employeesApi.leaveBalance(employeeId, year),
    enabled: Boolean(open && employeeId && leaveType === 'ANNUAL'),
  })

  const mutation = useMutation({
    mutationFn: (v) =>
      leaveApi.create({
        employee_id: v.employee_id,
        leave_type: v.leave_type,
        start_date: toApiDate(v.range[0]),
        end_date: toApiDate(v.range[1]),
        reason: v.reason || null,
      }),
    onSuccess: () => {
      message.success('Leave request submitted; approvers have been notified')
      queryClient.invalidateQueries({ queryKey: ['leave'] })
      queryClient.invalidateQueries({ queryKey: ['leave-balance'] })
      form.resetFields()
      onClose()
    },
    onError: (error) => {
      if (!applyFieldErrors(form, error)) message.error(errorMessage(error))
    },
  })

  return (
    <Modal
      title="Request leave"
      open={open}
      onCancel={onClose}
      onOk={() => form.submit()}
      okText="Submit request"
      confirmLoading={mutation.isPending}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" onFinish={mutation.mutate} initialValues={{ leave_type: 'ANNUAL' }}>
        <Form.Item name="employee_id" label="Employee" rules={[{ required: true }]}>
          <RemoteSelect
            queryKey={['employees']}
            fetcher={employeesApi.list}
            labelOf={employeeLabel}
            placeholder="Choose the employee"
          />
        </Form.Item>
        <Form.Item name="leave_type" label="Type of leave" rules={[{ required: true }]}>
          <Select options={LEAVE_TYPES} />
        </Form.Item>
        <Form.Item
          name="range"
          label="Dates"
          rules={[{ required: true, message: 'Choose the first and last day' }]}
          extra={days ? `${days} working day${days === 1 ? '' : 's'} (weekends are not counted)` : null}
        >
          <DatePicker.RangePicker style={{ width: '100%' }} />
        </Form.Item>
        {leaveType === 'ANNUAL' && balance.data && (
          <Alert
            type={days > Number(balance.data.remaining) ? 'warning' : 'info'}
            showIcon
            style={{ marginBottom: 16 }}
            title={`${Number(balance.data.remaining)} of ${Number(balance.data.entitlement)} annual leave days left in ${year}`}
          />
        )}
        <Form.Item name="reason" label="Reason">
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  )
}

export default function LeavePage() {
  const { can } = useAuth()
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const [filters, setFilters] = useState({ status: 'PENDING' })
  const [requesting, setRequesting] = useState(false)
  const set = (patch) => setFilters((f) => ({ ...f, ...patch }))
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['leave'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard'] })
  }

  const decide = useMutation({
    mutationFn: ({ action, leave, comment }) => {
      if (action === 'approve') return leaveApi.approve(leave.id, comment)
      if (action === 'reject') return leaveApi.reject(leave.id, comment)
      return leaveApi.cancel(leave.id)
    },
    onSuccess: (saved) => {
      message.success(`Leave request ${saved.status.toLowerCase()}`)
      refresh()
    },
    onError: (error) => message.error(errorMessage(error)),
  })

  const askComment = (action, leave) => {
    let comment = ''
    modal.confirm({
      title: action === 'approve' ? `Approve leave for ${leave.employee_name}?` : `Reject leave for ${leave.employee_name}?`,
      content: (
        <Input.TextArea
          rows={3}
          placeholder={action === 'approve' ? 'Comment (optional)' : 'Reason for rejecting (required)'}
          onChange={(e) => {
            comment = e.target.value
          }}
        />
      ),
      okText: action === 'approve' ? 'Approve' : 'Reject',
      okButtonProps: { danger: action === 'reject' },
      onOk: () => {
        if (action === 'reject' && comment.trim().length < 3) {
          message.warning('Please give a reason for rejecting')
          return Promise.reject(new Error('reason required'))
        }
        return decide.mutateAsync({ action, leave, comment: comment.trim() || undefined })
      },
    })
  }

  const actions = (l) => {
    const items = []
    if (l.status === 'PENDING' && can('leave.approve')) {
      items.push({ key: 'approve', label: 'Approve' }, { key: 'reject', label: 'Reject', danger: true })
    }
    const future = dayjs(l.start_date).isAfter(dayjs(), 'day')
    if (can('leave.create') && (l.status === 'PENDING' || (l.status === 'APPROVED' && future))) {
      items.push({ key: 'cancel', label: 'Cancel request' })
    }
    return items
  }

  const onAction = (key, l) => {
    if (key === 'approve' || key === 'reject') return askComment(key, l)
    return modal.confirm({
      title: `Cancel this leave request for ${l.employee_name}?`,
      okText: 'Cancel request',
      cancelText: 'Keep it',
      onOk: () => decide.mutateAsync({ action: 'cancel', leave: l }),
    })
  }

  return (
    <>
      <PageHeader
        title="Leave"
        subtitle="Requests, approvals and balances. Days are counted Monday to Friday."
        actions={
          can('leave.create') && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setRequesting(true)}>
              Request leave
            </Button>
          )
        }
      />
      <DataTable
        queryKey={['leave']}
        fetcher={leaveApi.list}
        filters={filters}
        defaultSort={{ field: 'start_date', order: 'desc' }}
        searchPlaceholder="Search employee name or number"
        toolbar={
          <>
            <Select
              allowClear
              placeholder="Any status"
              style={{ width: 150 }}
              value={filters.status}
              onChange={(status) => set({ status })}
              options={['PENDING', 'APPROVED', 'REJECTED', 'CANCELLED'].map((s) => ({ value: s, label: humanize(s) }))}
            />
            <Select
              allowClear
              placeholder="Any type"
              style={{ width: 160 }}
              value={filters.leave_type}
              onChange={(leave_type) => set({ leave_type })}
              options={LEAVE_TYPES}
            />
            <DatePicker.RangePicker
              onChange={(r) => set({ date_from: toApiDate(r?.[0]) || undefined, date_to: toApiDate(r?.[1]) || undefined })}
            />
          </>
        }
        columns={[
          {
            title: 'Employee',
            key: 'employee',
            render: (_, l) => (
              <div>
                <Typography.Text strong>{l.employee_name}</Typography.Text>
                <div className="muted" style={{ fontSize: 12 }}>
                  {l.employee_number}
                </div>
              </div>
            ),
          },
          { title: 'Type', dataIndex: 'leave_type', key: 'type', render: humanize },
          {
            title: 'Dates',
            key: 'start_date',
            sortField: 'start_date',
            render: (_, l) => `${formatDate(l.start_date)} – ${formatDate(l.end_date)}`,
          },
          { title: 'Days', dataIndex: 'days', key: 'days', align: 'right', render: (d) => Number(d) },
          { title: 'Status', dataIndex: 'status', key: 'status', sortField: 'status', render: (s) => <StatusTag status={s} /> },
          { title: 'Reason', dataIndex: 'reason', key: 'reason', render: (v) => v || '—' },
          {
            title: 'Decision',
            key: 'review',
            render: (_, l) =>
              l.reviewed_at ? (
                <span>
                  {formatDateTime(l.reviewed_at)}
                  {l.review_comment && <div className="muted" style={{ fontSize: 12 }}>{l.review_comment}</div>}
                </span>
              ) : (
                '—'
              ),
          },
          {
            title: '',
            key: 'actions',
            fixed: 'right',
            width: 56,
            render: (_, l) => {
              const items = actions(l)
              return items.length ? (
                <Dropdown trigger={['click']} placement="bottomRight" menu={{ items, onClick: ({ key }) => onAction(key, l) }}>
                  <Button type="text" icon={<MoreOutlined />} aria-label={`Actions for ${l.employee_name}`} />
                </Dropdown>
              ) : null
            },
          },
        ]}
      />
      <RequestLeaveModal open={requesting} onClose={() => setRequesting(false)} />
    </>
  )
}
