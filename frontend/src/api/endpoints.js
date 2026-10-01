import { api, cleanParams, unwrap } from './client'

/** Standard list/get/create/update/delete calls for a REST collection. */
export function resource(path) {
  return {
    list: (params = {}) => api.get(path, { params: cleanParams(params) }).then(unwrap),
    get: (id) => api.get(`${path}/${id}`).then(unwrap),
    create: (body) => api.post(path, body).then(unwrap),
    update: (id, body) => api.put(`${path}/${id}`, body).then(unwrap),
    remove: (id) => api.delete(`${path}/${id}`).then(unwrap),
  }
}

export const authApi = {
  login: (identifier, password) =>
    api.post('/auth/login', { identifier, password }, { skipAuth: true }).then(unwrap),
  me: () => api.get('/auth/me').then(unwrap),
  logout: (body) => api.post('/auth/logout', body).then(unwrap),
  changePassword: (body) => api.post('/auth/change-password', body).then(unwrap),
  forgotPassword: (email) =>
    api.post('/auth/forgot-password', { email }, { skipAuth: true }).then((r) => r.data),
  resetPassword: (token, newPassword) =>
    api
      .post('/auth/reset-password', { token, new_password: newPassword }, { skipAuth: true })
      .then((r) => r.data),
}

export const usersApi = {
  ...resource('/users'),
  setStatus: (id, status) => api.patch(`/users/${id}/status`, { status }).then(unwrap),
  setRoles: (id, roleIds) => api.put(`/users/${id}/roles`, { role_ids: roleIds }).then(unwrap),
  resetPassword: (id, newPassword) =>
    api.post(`/users/${id}/reset-password`, { new_password: newPassword }).then(unwrap),
}

export const rolesApi = resource('/roles')

export const permissionsApi = {
  list: () => api.get('/permissions').then(unwrap),
}

export const dashboardApi = {
  summary: () => api.get('/dashboard/summary').then(unwrap),
}

export const notificationsApi = {
  list: (params = {}) => api.get('/notifications', { params: cleanParams(params) }).then(unwrap),
  unreadCount: () => api.get('/notifications/unread-count').then(unwrap),
  markRead: (id) => api.post(`/notifications/${id}/read`).then(unwrap),
  markAllRead: () => api.post('/notifications/read-all').then(unwrap),
}

// ---------------------------------------------------------------- company
export const companyApi = {
  get: () => api.get('/company').then(unwrap),
  update: (body) => api.put('/company', body).then(unwrap),
}
export const branchesApi = resource('/branches')
export const departmentsApi = resource('/departments')
export const settingsApi = {
  get: () => api.get('/settings').then(unwrap),
  update: (body) => api.put('/settings', body).then(unwrap),
}

// ---------------------------------------------------------------- HR
export const employeesApi = {
  ...resource('/employees'),
  terminate: (id, body) => api.post(`/employees/${id}/terminate`, body).then(unwrap),
  leaveBalance: (id, year) =>
    api.get(`/employees/${id}/leave-balance`, { params: cleanParams({ year }) }).then(unwrap),
}
export const leaveApi = {
  list: (params = {}) => api.get('/leave-requests', { params: cleanParams(params) }).then(unwrap),
  create: (body) => api.post('/leave-requests', body).then(unwrap),
  approve: (id, comment) =>
    api.post(`/leave-requests/${id}/approve`, comment ? { comment } : {}).then(unwrap),
  reject: (id, comment) => api.post(`/leave-requests/${id}/reject`, { comment }).then(unwrap),
  cancel: (id) => api.post(`/leave-requests/${id}/cancel`).then(unwrap),
}

// ---------------------------------------------------------------- master data
export const customersApi = resource('/customers')
export const suppliersApi = resource('/suppliers')
export const categoriesApi = resource('/product-categories')
export const productsApi = resource('/products')
export const warehousesApi = resource('/warehouses')

// ---------------------------------------------------------------- inventory
export const inventoryApi = {
  stockLevels: (params = {}) =>
    api.get('/inventory/stock-levels', { params: cleanParams(params) }).then(unwrap),
  productStock: (productId) => api.get(`/inventory/products/${productId}`).then(unwrap),
  lowStock: (params = {}) =>
    api.get('/inventory/low-stock', { params: cleanParams(params) }).then(unwrap),
  movements: (params = {}) =>
    api.get('/inventory/movements', { params: cleanParams(params) }).then(unwrap),
  adjust: (body) => api.post('/inventory/adjustments', body).then(unwrap),
  transfer: (body) => api.post('/inventory/transfers', body).then(unwrap),
}

// ---------------------------------------------------------------- sales
export const quotationsApi = {
  ...resource('/sales/quotations'),
  setStatus: (id, status) => api.post(`/sales/quotations/${id}/status`, { status }).then(unwrap),
  convert: (id, body = {}) => api.post(`/sales/quotations/${id}/convert`, body).then(unwrap),
  pdfPath: (id) => `/sales/quotations/${id}/pdf`,
}

export const invoicesApi = {
  ...resource('/sales/invoices'),
  approve: (id) => api.post(`/sales/invoices/${id}/approve`).then(unwrap),
  cancel: (id, reason) => api.post(`/sales/invoices/${id}/cancel`, { reason }).then(unwrap),
  recordPayment: (id, body) => api.post(`/sales/invoices/${id}/payments`, body).then(unwrap),
  pdfPath: (id) => `/sales/invoices/${id}/pdf`,
}

export const paymentsApi = {
  list: (params = {}) => api.get('/sales/payments', { params: cleanParams(params) }).then(unwrap),
  void: (id, reason) => api.post(`/sales/payments/${id}/void`, { reason }).then(unwrap),
}

/** Fetch a file (e.g. a PDF) with the user's token and save it. */
export async function downloadFile(path, filename) {
  const response = await api.get(path, { responseType: 'blob' })
  const url = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}
