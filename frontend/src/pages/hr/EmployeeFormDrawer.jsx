import { useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Col,
  DatePicker,
  Divider,
  Drawer,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
} from 'antd'
import { branchesApi, departmentsApi, employeesApi, usersApi } from '../../api/endpoints'
import { applyFieldErrors, errorMessage } from '../../api/errors'
import { useAuth } from '../../auth/AuthContext'
import { emptyToNull, tpinRule } from '../../components/fields'
import RemoteSelect from '../../components/RemoteSelect'
import { fromApiDate, toApiDate } from '../../utils/dates'

export const employeeLabel = (e) => `${e.employee_number} · ${e.full_name}`
const refLabel = (r) => `${r.code} · ${r.name}`
const userLabel = (u) => `${u.full_name} (${u.email})`

const OPTIONAL_TEXT = [
  'middle_name',
  'gender',
  'national_id',
  'napsa_number',
  'tpin',
  'email',
  'phone',
  'address',
  'branch_id',
  'department_id',
  'manager_id',
  'user_id',
  'job_title',
  'emergency_contact_name',
  'emergency_contact_phone',
  'bank_name',
  'bank_account_number',
]
const SALARY_FIELDS = ['basic_salary', 'bank_name', 'bank_account_number']

export const EMPLOYMENT_TYPES = [
  { value: 'PERMANENT', label: 'Permanent' },
  { value: 'CONTRACT', label: 'Contract' },
  { value: 'CASUAL', label: 'Casual' },
  { value: 'INTERN', label: 'Intern' },
]

function toFormValues(e) {
  return {
    ...e,
    branch_id: e.branch?.id || null,
    department_id: e.department?.id || null,
    date_of_birth: fromApiDate(e.date_of_birth),
    hire_date: fromApiDate(e.hire_date),
    basic_salary: e.basic_salary === null ? null : Number(e.basic_salary),
  }
}

/** Create (employee = null) or edit an employee. */
export default function EmployeeFormDrawer({ open, employee, onClose }) {
  const [form] = Form.useForm()
  const { message } = App.useApp()
  const { can } = useAuth()
  const queryClient = useQueryClient()
  const editing = Boolean(employee)
  const seesSalary = can('employees.view_salary')

  useEffect(() => {
    if (!open) return
    form.resetFields()
    form.setFieldsValue(employee ? toFormValues(employee) : { employment_type: 'PERMANENT' })
  }, [open, employee, form])

  const mutation = useMutation({
    mutationFn: (values) => {
      const body = emptyToNull(values, OPTIONAL_TEXT)
      body.date_of_birth = toApiDate(values.date_of_birth)
      body.hire_date = toApiDate(values.hire_date)
      body.basic_salary =
        values.basic_salary === null || values.basic_salary === undefined
          ? null
          : String(values.basic_salary)
      // Without salary permission these fields are hidden (and blank in the API response);
      // sending them would erase the stored values.
      if (!seesSalary) for (const f of SALARY_FIELDS) delete body[f]
      if (!can('users.view')) delete body.user_id
      if (!editing) delete body.status
      return editing ? employeesApi.update(employee.id, body) : employeesApi.create(body)
    },
    onSuccess: (saved) => {
      message.success(editing ? `${saved.full_name} updated` : `${saved.full_name} added as ${saved.employee_number}`)
      queryClient.invalidateQueries({ queryKey: ['employees'] })
      onClose()
    },
    onError: (error) => {
      if (!applyFieldErrors(form, error)) message.error(errorMessage(error))
    },
  })

  const col = { xs: 24, sm: 12, lg: 8 }

  return (
    <Drawer
      title={editing ? `Edit ${employee.full_name} (${employee.employee_number})` : 'New employee'}
      open={open}
      onClose={onClose}
      size={880}
      destroyOnHidden
      extra={
        <Space>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="primary" loading={mutation.isPending} onClick={() => form.submit()}>
            {editing ? 'Save changes' : 'Add employee'}
          </Button>
        </Space>
      }
    >
      <Form form={form} layout="vertical" onFinish={mutation.mutate} requiredMark="optional">
        <Divider titlePlacement="start" plain style={{ marginTop: 0 }}>
          Personal details
        </Divider>
        <Row gutter={16}>
          <Col {...col}>
            <Form.Item name="first_name" label="First name" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col {...col}>
            <Form.Item name="middle_name" label="Middle name">
              <Input />
            </Form.Item>
          </Col>
          <Col {...col}>
            <Form.Item name="last_name" label="Last name" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col {...col}>
            <Form.Item name="gender" label="Gender">
              <Select
                allowClear
                options={[
                  { value: 'FEMALE', label: 'Female' },
                  { value: 'MALE', label: 'Male' },
                  { value: 'OTHER', label: 'Other' },
                ]}
              />
            </Form.Item>
          </Col>
          <Col {...col}>
            <Form.Item name="date_of_birth" label="Date of birth">
              <DatePicker style={{ width: '100%' }} disabledDate={(d) => d && d.isAfter(new Date())} />
            </Form.Item>
          </Col>
          <Col {...col}>
            <Form.Item name="national_id" label="NRC number">
              <Input placeholder="123456/10/1" />
            </Form.Item>
          </Col>
          <Col {...col}>
            <Form.Item name="napsa_number" label="NAPSA number">
              <Input />
            </Form.Item>
          </Col>
          <Col {...col}>
            <Form.Item name="tpin" label="TPIN" rules={[tpinRule]}>
              <Input maxLength={10} />
            </Form.Item>
          </Col>
          <Col {...col}>
            <Form.Item name="phone" label="Phone">
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} lg={8}>
            <Form.Item name="email" label="Email" rules={[{ type: 'email' }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} lg={16}>
            <Form.Item name="address" label="Address">
              <Input />
            </Form.Item>
          </Col>
        </Row>

        <Divider titlePlacement="start" plain>
          Employment
        </Divider>
        <Row gutter={16}>
          <Col {...col}>
            <Form.Item name="job_title" label="Job title">
              <Input />
            </Form.Item>
          </Col>
          <Col {...col}>
            <Form.Item name="employment_type" label="Employment type" rules={[{ required: true }]}>
              <Select options={EMPLOYMENT_TYPES} />
            </Form.Item>
          </Col>
          <Col {...col}>
            <Form.Item name="hire_date" label="Hire date" rules={[{ required: true }]}>
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col {...col}>
            <Form.Item name="department_id" label="Department">
              <RemoteSelect
                queryKey={['departments']}
                fetcher={departmentsApi.list}
                extraParams={{ is_active: true }}
                labelOf={refLabel}
                selected={employee?.department}
              />
            </Form.Item>
          </Col>
          <Col {...col}>
            <Form.Item name="branch_id" label="Branch">
              <RemoteSelect
                queryKey={['branches']}
                fetcher={branchesApi.list}
                extraParams={{ is_active: true }}
                labelOf={refLabel}
                selected={employee?.branch}
              />
            </Form.Item>
          </Col>
          <Col {...col}>
            <Form.Item name="manager_id" label="Reports to">
              <RemoteSelect
                queryKey={['employees']}
                fetcher={employeesApi.list}
                labelOf={employeeLabel}
                placeholder="No manager"
              />
            </Form.Item>
          </Col>
          {editing && (
            <Col {...col}>
              <Form.Item name="status" label="Status" rules={[{ required: true }]}>
                <Select
                  options={[
                    { value: 'ACTIVE', label: 'Active' },
                    { value: 'ON_LEAVE', label: 'On leave' },
                    { value: 'SUSPENDED', label: 'Suspended' },
                  ]}
                />
              </Form.Item>
            </Col>
          )}
          {can('users.view') && (
            <Col xs={24} lg={16}>
              <Form.Item
                name="user_id"
                label="System user account"
                extra="Link the user account this employee signs in with. Terminating the employee deactivates it."
              >
                <RemoteSelect
                  queryKey={['users']}
                  fetcher={usersApi.list}
                  labelOf={userLabel}
                  placeholder="Not linked"
                />
              </Form.Item>
            </Col>
          )}
        </Row>

        {seesSalary ? (
          <>
            <Divider titlePlacement="start" plain>
              Pay
            </Divider>
            <Row gutter={16}>
              <Col {...col}>
                <Form.Item name="basic_salary" label="Basic salary (ZMW per month)">
                  <InputNumber min={0} precision={2} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col {...col}>
                <Form.Item name="bank_name" label="Bank">
                  <Input />
                </Form.Item>
              </Col>
              <Col {...col}>
                <Form.Item name="bank_account_number" label="Account number">
                  <Input />
                </Form.Item>
              </Col>
            </Row>
          </>
        ) : (
          <Alert
            type="info"
            showIcon
            style={{ margin: '8px 0 16px' }}
            title="Salary and bank details are hidden. They need the 'view salary' permission."
          />
        )}

        <Divider titlePlacement="start" plain>
          Emergency contact
        </Divider>
        <Row gutter={16}>
          <Col xs={24} sm={12}>
            <Form.Item name="emergency_contact_name" label="Name">
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} sm={12}>
            <Form.Item name="emergency_contact_phone" label="Phone">
              <Input />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Drawer>
  )
}
