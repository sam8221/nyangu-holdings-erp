import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Badge, Button, Empty, Popover, Spin, Typography } from 'antd'
import { BellOutlined } from '@ant-design/icons'
import { notificationsApi } from '../api/endpoints'
import { formatDateTime } from '../utils/format'

const CATEGORY_COLORS = { APPROVAL: '#1e88e5', ALERT: '#e53935', SUCCESS: '#43a047', INFO: '#90a4ae' }

export default function NotificationBell() {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)

  const count = useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: notificationsApi.unreadCount,
    refetchInterval: 60_000,
  })
  const latest = useQuery({
    queryKey: ['notifications', 'latest'],
    queryFn: () => notificationsApi.list({ page: 1, page_size: 8 }),
    enabled: open,
  })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['notifications'] })
  const markRead = useMutation({ mutationFn: notificationsApi.markRead, onSuccess: refresh })
  const markAll = useMutation({ mutationFn: notificationsApi.markAllRead, onSuccess: refresh })

  const unread = count.data?.unread || 0
  const items = latest.data?.items || []

  const content = (
    <div style={{ width: 340 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <Typography.Text strong>Notifications</Typography.Text>
        <Button
          type="link"
          size="small"
          disabled={!unread}
          loading={markAll.isPending}
          onClick={() => markAll.mutate()}
        >
          Mark all as read
        </Button>
      </div>
      {latest.isLoading ? (
        <div style={{ textAlign: 'center', padding: 24 }}>
          <Spin />
        </div>
      ) : items.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No notifications" />
      ) : (
        <div style={{ maxHeight: 360, overflowY: 'auto' }}>
          {items.map((note) => (
            <div
              key={note.id}
              role="button"
              tabIndex={0}
              onClick={() => !note.is_read && markRead.mutate(note.id)}
              onKeyDown={(e) => e.key === 'Enter' && !note.is_read && markRead.mutate(note.id)}
              style={{
                padding: '8px 10px',
                marginBottom: 4,
                borderRadius: 6,
                cursor: note.is_read ? 'default' : 'pointer',
                background: note.is_read ? 'transparent' : '#e3f2fd',
                borderLeft: `3px solid ${CATEGORY_COLORS[note.category] || '#90a4ae'}`,
              }}
            >
              <Typography.Text strong={!note.is_read}>{note.title}</Typography.Text>
              <div style={{ fontSize: 12, color: '#52606d' }}>{note.message}</div>
              <div style={{ fontSize: 11, color: '#8a99ab' }}>{formatDateTime(note.created_at)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )

  return (
    <Popover
      content={content}
      trigger="click"
      placement="bottomRight"
      open={open}
      onOpenChange={setOpen}
    >
      <Badge count={unread} size="small" offset={[-2, 4]}>
        <Button
          type="text"
          shape="circle"
          aria-label={`Notifications${unread ? ` (${unread} unread)` : ''}`}
          icon={<BellOutlined style={{ fontSize: 18 }} />}
        />
      </Badge>
    </Popover>
  )
}
