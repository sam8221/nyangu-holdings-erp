/** True if the user holds every permission (Super Administrators hold all). */
export function hasAll(user, perms) {
  if (!user) return false
  if (user.is_super_admin) return true
  return perms.every((p) => user.permissions.includes(p))
}

/** True if the user holds at least one of the permissions. An empty list means "signed in". */
export function hasAny(user, perms) {
  if (!user) return false
  if (!perms || perms.length === 0 || user.is_super_admin) return true
  return perms.some((p) => user.permissions.includes(p))
}
