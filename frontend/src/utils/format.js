import dayjs from 'dayjs'

// The API sends money and quantities as decimal strings ("1500.00"); these helpers only format
// them for display. Never do arithmetic on the formatted values.

const moneyFormat = new Intl.NumberFormat('en-GB', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const quantityFormat = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 3 })

export function formatMoney(value, currency = 'ZMW') {
  if (value === null || value === undefined || value === '') return '—'
  const number = Number(value)
  if (Number.isNaN(number)) return String(value)
  const text = moneyFormat.format(Math.abs(number))
  return `${number < 0 ? '-' : ''}${currency ? `${currency} ` : ''}${text}`
}

export function formatQuantity(value) {
  if (value === null || value === undefined || value === '') return '—'
  const number = Number(value)
  return Number.isNaN(number) ? String(value) : quantityFormat.format(number)
}

export function formatDate(value) {
  return value ? dayjs(value).format('DD MMM YYYY') : '—'
}

export function formatDateTime(value) {
  return value ? dayjs(value).format('DD MMM YYYY, HH:mm') : '—'
}

/** "PARTIALLY_PAID" -> "Partially paid" */
export function humanize(value) {
  if (!value) return ''
  const text = String(value).replace(/[_.]/g, ' ').toLowerCase()
  return text.charAt(0).toUpperCase() + text.slice(1)
}
