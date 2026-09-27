/** A human-readable message for any API or network error. */
export function errorMessage(error, fallback = 'Something went wrong. Please try again.') {
  const data = error?.response?.data
  if (data?.message) return data.message
  if (error?.code === 'ECONNABORTED') return 'The server took too long to respond.'
  if (error && !error.response) return 'Cannot reach the server. Check your connection.'
  return fallback
}

/**
 * Show field-level API errors on an Ant Design form.
 * "lines.0.product_id" becomes the form path ['lines', 0, 'product_id'].
 * Returns true when at least one field error was shown.
 */
export function applyFieldErrors(form, error) {
  const errors = error?.response?.data?.errors
  if (!Array.isArray(errors)) return false
  const fields = errors
    .filter((e) => e.field)
    .map((e) => ({
      name: e.field.split('.').map((part) => (/^\d+$/.test(part) ? Number(part) : part)),
      errors: [e.message],
    }))
  if (fields.length) form.setFields(fields)
  return fields.length > 0
}
