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
