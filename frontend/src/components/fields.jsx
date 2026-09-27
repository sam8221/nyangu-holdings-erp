import { Select, Tag } from 'antd'

/** Reusable small pieces for forms and tables. */

export const ActiveTag = ({ active }) =>
  active ? <Tag color="green">Active</Tag> : <Tag>Inactive</Tag>

export const activeFilterOptions = [
  { value: true, label: 'Active' },
  { value: false, label: 'Inactive' },
]

export function ActiveFilter({ value, onChange }) {
  return (
    <Select
      allowClear
      placeholder="Active or inactive"
      style={{ width: 170 }}
      value={value}
      onChange={onChange}
      options={activeFilterOptions}
    />
  )
}

/** Validation rule for Zambian TPINs (10 digits). */
export const tpinRule = { pattern: /^\d{10}$/, message: 'A TPIN has exactly 10 digits' }

/** Normaliser for upper-case codes typed into inputs. */
export const upper = (value) => (value || '').toUpperCase()

/** Convert empty strings from inputs into null for optional API fields. */
export function emptyToNull(values, fields) {
  const copy = { ...values }
  for (const field of fields) if (copy[field] === '' || copy[field] === undefined) copy[field] = null
  return copy
}

export const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
].map((label, i) => ({ value: i + 1, label }))
