import { describe, expect, it } from 'vitest'
import { hasAll, hasAny } from '../auth/permissions'
import { visibleMenu } from '../layout/menu'
import { formatMoney, formatQuantity, humanize } from './format'
import { passwordProblems } from './password'

describe('formatMoney', () => {
  it('formats decimal strings from the API', () => {
    expect(formatMoney('1500.00')).toBe('ZMW 1,500.00')
    expect(formatMoney('-12.5')).toBe('-ZMW 12.50')
    expect(formatMoney('0')).toBe('ZMW 0.00')
    expect(formatMoney(null)).toBe('—')
    expect(formatMoney('99.9', '')).toBe('99.90')
  })
})

describe('formatQuantity and humanize', () => {
  it('trims trailing zeros and humanises codes', () => {
    expect(formatQuantity('12.500')).toBe('12.5')
    expect(formatQuantity('1000.000')).toBe('1,000')
    expect(humanize('PARTIALLY_PAID')).toBe('Partially paid')
  })
})

describe('permissions', () => {
  const clerk = { is_super_admin: false, permissions: ['users.view', 'dashboard.view'] }
  const boss = { is_super_admin: true, permissions: [] }

  it('checks all and any', () => {
    expect(hasAll(clerk, ['users.view'])).toBe(true)
    expect(hasAll(clerk, ['users.view', 'users.create'])).toBe(false)
    expect(hasAny(clerk, ['users.create', 'dashboard.view'])).toBe(true)
    expect(hasAny(clerk, [])).toBe(true)
    expect(hasAll(boss, ['anything.at_all'])).toBe(true)
    expect(hasAny(null, ['users.view'])).toBe(false)
  })

  it('builds a menu with only permitted entries', () => {
    const menu = visibleMenu(clerk)
    expect(menu.map((m) => m.key)).toEqual(['/dashboard', 'admin'])
    expect(menu[1].children.map((c) => c.key)).toEqual(['/users'])
    expect(menu[0].perms).toBeUndefined()
    expect(visibleMenu(boss).length).toBeGreaterThan(5)
  })
})

describe('passwordProblems', () => {
  it('mirrors the server policy', () => {
    expect(passwordProblems('Str0ng!Passw0rd')).toEqual([])
    expect(passwordProblems('short')).toEqual([
      'at least 10 characters',
      'an uppercase letter',
      'a digit',
      'a symbol',
    ])
  })
})
