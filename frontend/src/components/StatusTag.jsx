import { Tag } from 'antd'
import { humanize } from '../utils/format'

const COLORS = {
  ACTIVE: 'green',
  INACTIVE: 'default',
  DRAFT: 'default',
  PENDING: 'gold',
  ISSUED: 'blue',
  APPROVED: 'green',
  PARTIALLY_PAID: 'gold',
  PARTIALLY_RECEIVED: 'gold',
  PAID: 'green',
  RECEIVED: 'green',
  POSTED: 'green',
  CLOSED: 'purple',
  SENT: 'blue',
  ACCEPTED: 'green',
  DECLINED: 'red',
  CONVERTED: 'purple',
  REJECTED: 'red',
  CANCELLED: 'red',
  VOIDED: 'red',
  TERMINATED: 'red',
  SUSPENDED: 'orange',
  ON_LEAVE: 'cyan',
  IN_USE: 'green',
  IN_STORE: 'blue',
  UNDER_MAINTENANCE: 'orange',
  DISPOSED: 'default',
}

export default function StatusTag({ status }) {
  if (!status) return null
  return (
    <Tag color={COLORS[status] || 'default'} style={{ marginInlineEnd: 0 }}>
      {humanize(status)}
    </Tag>
  )
}
