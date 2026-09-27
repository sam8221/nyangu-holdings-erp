import { useEffect, useEffectEvent, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { App, Button, Dropdown, Form, Modal } from 'antd'
import { MoreOutlined, PlusOutlined } from '@ant-design/icons'
import { applyFieldErrors, errorMessage } from '../api/errors'
import { useAuth } from '../auth/AuthContext'
import DataTable from './DataTable'
import PageHeader from './PageHeader'

/** Modal form used by CrudPage for both create (record = null) and edit. */
export function CrudFormModal({
  open,
  record,
  onClose,
  api,
  queryKey,
  entityLabel,
  FormFields,
  toFormValues,
  toPayload,
  initialValues,
  width,
}) {
  const [form] = Form.useForm()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const editing = Boolean(record)

  // Fill the form when the modal opens (not on every re-render, which would wipe typing).
  const fillForm = useEffectEvent(() => {
    form.resetFields()
    form.setFieldsValue(record ? toFormValues(record) : initialValues || {})
  })
  useEffect(() => {
    if (open) fillForm()
  }, [open, record])

  const mutation = useMutation({
    mutationFn: (values) => {
      const body = toPayload(values, record)
      return editing ? api.update(record.id, body) : api.create(body)
    },
    onSuccess: () => {
      message.success(editing ? `${entityLabel} updated` : `${entityLabel} created`)
      queryClient.invalidateQueries({ queryKey })
      onClose()
    },
    onError: (error) => {
      if (!applyFieldErrors(form, error)) message.error(errorMessage(error))
    },
  })

  return (
    <Modal
      title={editing ? `Edit ${entityLabel.toLowerCase()}` : `New ${entityLabel.toLowerCase()}`}
      open={open}
      onCancel={onClose}
      onOk={() => form.submit()}
      okText={editing ? 'Save changes' : 'Create'}
      confirmLoading={mutation.isPending}
      width={width}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" onFinish={mutation.mutate} requiredMark="optional">
        <FormFields form={form} record={record} editing={editing} />
      </Form>
    </Modal>
  )
}

const identity = (value) => value

/**
 * A complete list page for simple reference data: searchable table, create/edit modal and
 * delete with confirmation. Buttons appear only for users holding the matching permission.
 */
export default function CrudPage({
  title,
  subtitle,
  entityLabel,
  queryKey,
  api,
  columns,
  filters,
  filterBar,
  perms = {},
  FormFields,
  toFormValues = identity,
  toPayload = identity,
  initialValues,
  formWidth = 640,
  searchPlaceholder,
  defaultSort,
  describe = (record) => record.name,
  extraActions,
  headerActions,
  embedded = false,
}) {
  const { can } = useAuth()
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState({ open: false, record: null })

  const remove = useMutation({
    mutationFn: (record) => api.remove(record.id),
    onSuccess: () => {
      message.success(`${entityLabel} deleted`)
      queryClient.invalidateQueries({ queryKey })
    },
    onError: (error) => message.error(errorMessage(error)),
  })

  const actionItems = (record) => {
    const items = []
    if (perms.update && can(perms.update)) items.push({ key: 'edit', label: 'Edit' })
    for (const action of extraActions?.(record) || []) items.push(action)
    if (perms.delete && can(perms.delete)) {
      if (items.length) items.push({ type: 'divider' })
      items.push({ key: 'delete', label: 'Delete', danger: true })
    }
    return items
  }

  const onAction = (key, record) => {
    if (key === 'edit') return setEditing({ open: true, record })
    if (key === 'delete') {
      return modal.confirm({
        title: `Delete ${describe(record)}?`,
        content: 'This cannot be undone. Records that are in use cannot be deleted; deactivate them instead.',
        okText: 'Delete',
        okButtonProps: { danger: true },
        onOk: () => remove.mutateAsync(record),
      })
    }
    return extraActions?.(record).find((a) => a.key === key)?.onClick?.(record)
  }

  const allColumns = [
    ...columns,
    {
      title: '',
      key: 'actions',
      fixed: 'right',
      width: 56,
      render: (_, record) => {
        const items = actionItems(record)
        return items.length ? (
          <Dropdown
            trigger={['click']}
            placement="bottomRight"
            menu={{ items, onClick: ({ key }) => onAction(key, record) }}
          >
            <Button type="text" icon={<MoreOutlined />} aria-label={`Actions for ${describe(record)}`} />
          </Dropdown>
        ) : null
      },
    },
  ]

  const actions = (
    <>
      {headerActions}
      {perms.create && can(perms.create) && (
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setEditing({ open: true, record: null })}
        >
          New {entityLabel.toLowerCase()}
        </Button>
      )}
    </>
  )

  return (
    <>
      {!embedded && <PageHeader title={title} subtitle={subtitle} actions={actions} />}
      <DataTable
        queryKey={queryKey}
        fetcher={api.list}
        columns={allColumns}
        filters={filters}
        toolbar={
          embedded ? (
            <>
              {filterBar}
              <div className="spacer" />
              {actions}
            </>
          ) : (
            filterBar
          )
        }
        searchPlaceholder={searchPlaceholder}
        defaultSort={defaultSort}
      />
      <CrudFormModal
        open={editing.open}
        record={editing.record}
        onClose={() => setEditing({ open: false, record: null })}
        api={api}
        queryKey={queryKey}
        entityLabel={entityLabel}
        FormFields={FormFields}
        toFormValues={toFormValues}
        toPayload={toPayload}
        initialValues={initialValues}
        width={formWidth}
      />
    </>
  )
}
