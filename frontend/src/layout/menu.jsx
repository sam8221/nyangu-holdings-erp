import {
  BankOutlined,
  BarChartOutlined,
  DashboardOutlined,
  DesktopOutlined,
  InboxOutlined,
  SettingOutlined,
  ShoppingCartOutlined,
  ShoppingOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import { hasAny } from '../auth/permissions'

/**
 * Sidebar structure. `perms` lists permissions of which the user needs at least one;
 * sections with no visible children are hidden.
 */
export const MENU = [
  { key: '/dashboard', label: 'Dashboard', icon: <DashboardOutlined />, perms: ['dashboard.view'] },
  {
    key: 'sales',
    label: 'Sales',
    icon: <ShoppingCartOutlined />,
    children: [
      { key: '/sales/invoices', label: 'Invoices', perms: ['sales.view'] },
      { key: '/sales/payments', label: 'Payments', perms: ['sales.view', 'finance.view'] },
      { key: '/customers', label: 'Customers', perms: ['customers.view'] },
    ],
  },
  {
    key: 'procurement',
    label: 'Procurement',
    icon: <ShoppingOutlined />,
    children: [
      { key: '/procurement/purchase-orders', label: 'Purchase orders', perms: ['procurement.view'] },
      {
        key: '/procurement/goods-receipts',
        label: 'Goods received',
        perms: ['procurement.view', 'inventory.view'],
      },
      { key: '/suppliers', label: 'Suppliers', perms: ['suppliers.view'] },
    ],
  },
  {
    key: 'inventory',
    label: 'Inventory',
    icon: <InboxOutlined />,
    children: [
      { key: '/products', label: 'Products', perms: ['products.view'] },
      { key: '/inventory/stock', label: 'Stock levels', perms: ['inventory.view'] },
      { key: '/inventory/movements', label: 'Stock movements', perms: ['inventory.view'] },
      { key: '/warehouses', label: 'Warehouses', perms: ['inventory.view', 'company.update'] },
    ],
  },
  {
    key: 'finance',
    label: 'Finance',
    icon: <BankOutlined />,
    children: [
      { key: '/finance/expenses', label: 'Expenses', perms: ['finance.view'] },
      { key: '/finance/bills', label: 'Supplier bills', perms: ['finance.view'] },
      { key: '/finance/receivables', label: 'Receivables', perms: ['finance.view'] },
      { key: '/finance/payables', label: 'Payables', perms: ['finance.view'] },
    ],
  },
  {
    key: 'hr',
    label: 'HR',
    icon: <TeamOutlined />,
    children: [
      { key: '/employees', label: 'Employees', perms: ['employees.view'] },
      { key: '/leave', label: 'Leave', perms: ['leave.view'] },
    ],
  },
  { key: '/assets', label: 'Assets', icon: <DesktopOutlined />, perms: ['assets.view'] },
  { key: '/reports', label: 'Reports', icon: <BarChartOutlined />, perms: ['reports.view'] },
  {
    key: 'admin',
    label: 'Administration',
    icon: <SettingOutlined />,
    children: [
      { key: '/users', label: 'Users', perms: ['users.view'] },
      { key: '/roles', label: 'Roles', perms: ['roles.view'] },
      { key: '/audit-logs', label: 'Audit log', perms: ['audit.view'] },
      { key: '/company', label: 'Company', perms: ['company.view'] },
      { key: '/settings', label: 'Settings', perms: ['settings.view'] },
    ],
  },
]

/** The menu items this user may see, in Ant Design Menu format. */
export function visibleMenu(user) {
  const strip = ({ perms: _perms, ...item }) => item
  return MENU.flatMap((item) => {
    if (item.children) {
      const children = item.children.filter((c) => hasAny(user, c.perms)).map(strip)
      return children.length ? [{ ...strip(item), children }] : []
    }
    return hasAny(user, item.perms) ? [strip(item)] : []
  })
}

/** Flat list of every page in the menu (used for routes and page titles). */
export const MENU_PAGES = MENU.flatMap((item) => (item.children ? item.children : [item]))

