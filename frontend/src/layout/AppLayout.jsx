import { useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { App, Avatar, Button, Dropdown, Grid, Layout, Menu, Space, Typography } from 'antd'
import {
  KeyOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { useAuth } from '../auth/AuthContext'
import logo from '../assets/logo.jpg'
import { colors } from '../theme'
import ChangePasswordModal from './ChangePasswordModal'
import NotificationBell from './NotificationBell'
import { MENU, visibleMenu } from './menu'

const { Header, Sider, Content } = Layout

function openSectionFor(pathname) {
  const section = MENU.find((item) => item.children?.some((c) => pathname.startsWith(c.key)))
  return section ? [section.key] : []
}

function selectedKeyFor(pathname) {
  const keys = MENU.flatMap((item) => (item.children ? item.children : [item])).map((i) => i.key)
  // Longest match wins, so /sales/invoices/123 highlights "Invoices".
  return keys.filter((k) => pathname === k || pathname.startsWith(`${k}/`)).sort((a, b) => b.length - a.length)[0]
}

export default function AppLayout() {
  const { user, logout } = useAuth()
  const { modal } = App.useApp()
  const navigate = useNavigate()
  const location = useLocation()
  const screens = Grid.useBreakpoint()
  const [collapsed, setCollapsed] = useState(false)
  const [passwordOpen, setPasswordOpen] = useState(false)
  const [openKeys, setOpenKeys] = useState(() => openSectionFor(location.pathname))

  const selected = selectedKeyFor(location.pathname)
  const roleNames = user.roles.map((r) => r.display_name).join(', ') || 'No role'

  const userMenu = {
    items: [
      { key: 'who', label: <span className="muted">{user.email}</span>, disabled: true },
      { type: 'divider' },
      { key: 'password', icon: <KeyOutlined />, label: 'Change password' },
      { key: 'logout', icon: <LogoutOutlined />, label: 'Sign out' },
      { key: 'logout-all', icon: <LogoutOutlined />, label: 'Sign out of all devices' },
    ],
    onClick: ({ key }) => {
      if (key === 'password') setPasswordOpen(true)
      if (key === 'logout') logout()
      if (key === 'logout-all') {
        modal.confirm({
          title: 'Sign out of all devices?',
          content: 'Every session of your account, on every device, will end.',
          okText: 'Sign out everywhere',
          onOk: () => logout({ allDevices: true }),
        })
      }
    },
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        width={236}
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        breakpoint="lg"
        collapsedWidth={screens.xs ? 0 : 72}
        trigger={null}
        style={{ borderRight: `1px solid ${colors.lightBlueBorder}` }}
      >
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            justifyContent: collapsed ? 'center' : 'flex-start',
            gap: 10,
            padding: collapsed ? 0 : '0 20px',
            borderBottom: `1px solid ${colors.lightBlue}`,
          }}
        >
          <img src={logo} alt="Nyangu Holdings" style={{ width: 44, height: 44, objectFit: 'contain' }} />
          {!collapsed && (
            <div style={{ lineHeight: 1.15 }}>
              <div style={{ fontWeight: 700, color: colors.primaryDark }}>Nyangu Holdings</div>
              <div style={{ fontSize: 12, color: colors.muted }}>ERP</div>
            </div>
          )}
        </div>
        <Menu
          mode="inline"
          items={visibleMenu(user)}
          selectedKeys={selected ? [selected] : []}
          openKeys={collapsed ? undefined : openKeys}
          onOpenChange={setOpenKeys}
          onClick={({ key }) => navigate(key)}
          style={{ borderInlineEnd: 0, paddingTop: 8 }}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 16px',
            borderBottom: `1px solid ${colors.lightBlueBorder}`,
            position: 'sticky',
            top: 0,
            zIndex: 10,
          }}
        >
          <Button
            type="text"
            aria-label={collapsed ? 'Expand menu' : 'Collapse menu'}
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
          />
          <Space size="middle">
            <NotificationBell />
            <Dropdown menu={userMenu} trigger={['click']} placement="bottomRight">
              <Button type="text" style={{ height: 48 }}>
                <Space>
                  <Avatar
                    size="small"
                    icon={<UserOutlined />}
                    style={{ background: colors.lightBlue, color: colors.primaryDark }}
                  />
                  {!screens.xs && (
                    <span style={{ textAlign: 'left', lineHeight: 1.2 }}>
                      <Typography.Text strong style={{ display: 'block' }}>
                        {user.full_name}
                      </Typography.Text>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {roleNames}
                      </Typography.Text>
                    </span>
                  )}
                </Space>
              </Button>
            </Dropdown>
          </Space>
        </Header>
        <Content style={{ padding: screens.xs ? 12 : 24 }}>
          <Outlet />
        </Content>
      </Layout>
      <ChangePasswordModal open={passwordOpen} onClose={() => setPasswordOpen(false)} />
    </Layout>
  )
}
