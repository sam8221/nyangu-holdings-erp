import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App,
  Button,
  DatePicker,
  Descriptions,
  Dropdown,
  Form,
  Input,
  Modal,
  Select,
  Spin,
  Typography,
} from 'antd'
import { MoreOutlined, PlusOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { branchesApi, departmentsApi, employeesApi } from '../../api/endpoints'
import { errorMessage } from '../../api/errors'
import { useAuth } from '../../auth/AuthContext'
import DataTable from '../../components/DataTable'
import PageHeader from '../../components/PageHeader'
import RemoteSelect from '../../components/RemoteSelect'
import StatusTag from '../../components/StatusTag'
import { toApiDate } from '../../utils/dates'
import { formatDate, formatMoney, humanize } from '../../utils/format'
import EmployeeFormDrawer, { EMPLOYMENT_TYPES } from './EmployeeFormDrawer'

const refLabel = (r) => `${r.code} · ${r.name}`

function TerminateModal({ employee, onClose }) {
  const [form] = Form.useForm()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: (v) =>
      employeesApi.terminate(employee.id, {
        termination_date: toApiDate(v.termination_date),
        reason: v.reason,
      }),
    onSuccess: (saved) => {
      message.success(`${saved.full_name} has been terminated`)
      queryClient.invalidateQueries({ queryKey: ['employees'] })
      onClose()
    },
    onError: (error) => message.error(errorMessage(error)),
  })
  return (
    <Modal
      title={employee ? `Terminate ${employee.full_name}` : 'Terminate'}
      open={Boolean(employee)}
      onCancel={onClose}
      onOk={() => form.submit()}
      okText="Terminate"
      okButtonProps={{ danger: true }}
      confirmLoading={mutation.isPending}
      destroyOnHidden
    >
      <Typography.Paragraph type="secondary">
        Their linked user account is deactivated and leave after this date is cancelled. This
        cannot be undone.
      </Typography.Paragraph>
      <Form
        form={form}
        layout="vertical"
        onFinish={mutation.mutate}
        initialValues={{ termination_date: dayjs() }}
      >
        <Form.Item name="termination_date" label="Last working day" rules={[{ required: true }]}>
          <DatePicker style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="reason" label="Reason" rules={[{ required: true, min: 3 }]}>
          <Input.TextArea rows={3} placeholder="e.g. End of contract, resignation" />
        </Form.Item>
      </Form>
    </Modal>
  )
}

function LeaveBalanceModal({ employee, onClose }) {
  const year = dayjs().year()
  const balance = useQuery({
    queryKey: ['leave-balance', employee?.id, year],
    queryFn: () => employeesApi.leaveBalance(employee.id, year),
    enabled: Boolean(employee),
  })
  const b = balance.data
  return (
    <Modal
      title={employee ? `Annual leave ${year}: ${employee.full_name}` : 'Leave balance'}
      open={Boolean(employee)}
      onCancel={onClose}
      footer={null}
    >
      {balance.isLoading && <Spin />}
      {balance.isError && <Typography.Text type="danger">{errorMessage(balance.error)}</Typography.Text>}
      {b && (
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label="Entitlement">{Number(b.entitlement)} days</Descriptions.Item>
          <Descriptions.Item label="Taken">{Number(b.taken)} days</Descriptions.Item>
          <Descriptions.Item label="Pending approval">{Number(b.pending)} days</Descriptions.Item>
          <Descriptions.Item label="Remaining">
            <Typography.Text strong>{Number(b.remaining)} days</Typography.Text>
          </Descriptions.Item>
        </Descriptions>
      )}
    </Modal>
  )
}

export default function EmployeesPage() {
  const { can } = useAuth()
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const [filters, setFilters] = useState({})
  const [drawer, setDrawer] = useState({ open: false, employee: null })
  const [terminating, setTerminating] = useState(null)
  const [balanceOf, setBalanceOf] = useState(null)
  const set = (patch) => setFilters((f) => ({ ...f, ...patch }))

  const remove = useMutation({
    mutationFn: (e) => employeesApi.remove(e.id),
    onSuccess: () => {
      message.success('Employee deleted')
      queryClient.invalidateQueries({ queryKey: ['employees'] })
    },
    onError: (error) => message.error(errorMessage(error)),
  })

  const actions = (e) => {
    const terminated = e.status === 'TERMINATED'
    const items = []
    if (can('employees.update') && !terminated) items.push({ key: 'edit', label: 'Edit' })
    if (can('leave.view')) items.push({ key: 'balance', label: 'Leave balance' })
    if (can('employees.update') && !terminated) {
      items.push({ type: 'divider' }, { key: 'terminate', label: 'Terminate', danger: true })
    }
    if (can('employees.delete')) items.push({ key: 'delete', label: 'Delete', danger: true })
    return items
  }

  const onAction = (key, e) => {
    if (key === 'edit') setDrawer({ open: true, employee: e })
    if (key === 'balance') setBalanceOf(e)
    if (key === 'terminate') setTerminating(e)
    if (key === 'delete') {
      modal.confirm({
        title: `Delete ${e.full_name}?`,
        content: 'Only employees with no leave history can be deleted. Terminate the others.',
        okText: 'Delete',
        okButtonProps: { danger: true },
        onOk: () => remove.mutateAsync(e),
      })
    }
  }

  const columns = [
    {
      title: 'Number',
      dataIndex: 'employee_number',
      key: 'employee_number',
      sortField: 'employee_number',
    },
    {
      title: 'Name',
      key: 'last_name',
      sortField: 'last_name',
      render: (_, e) => (
        <div>
          <Typography.Text strong>{e.full_name}</Typography.Text>
          <div className="muted" style={{ fontSize: 12 }}>
            {e.job_title || 'No job title'}
          </div>
        </div>
      ),
    },
    { title: 'Department', key: 'department', render: (_, e) => e.department?.name || '—' },
    { title: 'Branch', key: 'branch', render: (_, e) => e.branch?.name || '—' },
    { title: 'Type', dataIndex: 'employment_type', key: 'type', render: humanize },
    { title: 'Status', dataIndex: 'status', key: 'status', sortField: 'status', render: (s) => <StatusTag status={s} /> },
    { title: 'Hired', dataIndex: 'hire_date', key: 'hire_date', sortField: 'hire_date', render: formatDate },
  ]
  if (can('employees.view_salary')) {
    columns.push({
      title: 'Basic salary',
      dataIndex: 'basic_salary',
      key: 'salary',
      align: 'right',
      render: (v) => formatMoney(v),
    })
  }
  columns.push({
    title: '',
    key: 'actions',
    fixed: 'right',
    width: 56,
    render: (_, e) => {
      const items = actions(e)
      return items.length ? (
        <Dropdown trigger={['click']} placement="bottomRight" menu={{ items, onClick: ({ key }) => onAction(key, e) }}>
          <Button type="text" icon={<MoreOutlined />} aria-label={`Actions for ${e.full_name}`} />
        </Dropdown>
      ) : null
    },
  })

  return (
    <>
      <PageHeader
        title="Employees"
        subtitle="Staff records, departments and employment details."
        actions={
          can('employees.create') && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setDrawer({ open: true, employee: null })}>
              New employee
            </Button>
          )
        }
      />
      <DataTable
        queryKey={['employees']}
        fetcher={employeesApi.list}
        filters={filters}
        columns={columns}
        searchPlaceholder="Search name, number, NRC or job title"
        toolbar={
          <>
            <Select
              allowClear
              placeholder="Any status"
              style={{ width: 150 }}
              value={filters.status}
              onChange={(status) => set({ status })}
              options={['ACTIVE', 'ON_LEAVE', 'SUSPENDED', 'TERMINATED'].map((s) => ({ value: s, label: humanize(s) }))}
            />
            <Select
              allowClear
              placeholder="Any type"
              style={{ width: 150 }}
              value={filters.employment_type}
              onChange={(employment_type) => set({ employment_type })}
              options={EMPLOYMENT_TYPES}
            />
            <RemoteSelect
              queryKey={['departments']}
              fetcher={departmentsApi.list}
              labelOf={refLabel}
              placeholder="Any department"
              style={{ width: 200 }}
              value={filters.department_id}
              onChange={(department_id) => set({ department_id })}
            />
            <RemoteSelect
              queryKey={['branches']}
              fetcher={branchesApi.list}
              labelOf={refLabel}
              placeholder="Any branch"
              style={{ width: 180 }}
              value={filters.branch_id}
              onChange={(branch_id) => set({ branch_id })}
            />
          </>
        }
      />
      <EmployeeFormDrawer
        open={drawer.open}
        employee={drawer.employee}
        onClose={() => setDrawer({ open: false, employee: null })}
      />
      <TerminateModal employee={terminating} onClose={() => setTerminating(null)} />
      <LeaveBalanceModal employee={balanceOf} onClose={() => setBalanceOf(null)} />
    </>
  )
}
