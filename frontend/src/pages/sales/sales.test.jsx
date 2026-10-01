import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { authApi, quotationsApi } from '../../api/endpoints'
import { saveTokens } from '../../api/tokens'
import { renderWithProviders } from '../../test/render'
import { documentTotals, lineAmounts } from '../../utils/pricing'
import SalesDocumentDrawer from './SalesDocumentDrawer'

vi.mock('../../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal()
  const empty = vi.fn(async () => ({ items: [], meta: { page: 1, page_size: 50, total: 0, pages: 0 } }))
  return {
    ...actual,
    authApi: { ...actual.authApi, me: vi.fn() },
    quotationsApi: { ...actual.quotationsApi, update: vi.fn(), create: vi.fn() },
    customersApi: { ...actual.customersApi, list: empty },
    productsApi: { ...actual.productsApi, list: empty },
    warehousesApi: { ...actual.warehousesApi, list: empty },
    settingsApi: { ...actual.settingsApi, get: vi.fn() },
  }
})

// Nyangu's sample quotation: quantity and VAT-inclusive unit price.
const SAMPLE = [[15, 450], [15, 650], [20, 700], [30, 750], [40, 1250], [20, 1380], [20, 3450], [10, 3700], [6, 4000]]

describe('pricing preview', () => {
  it('matches the sample quotation to the ngwee', () => {
    const lines = SAMPLE.map(([quantity, unitPrice]) => lineAmounts({ quantity, unitPrice, taxRate: 16 }, true))
    expect(lines[0]).toMatchObject({ total: 6750, tax: 931.03 })
    expect(documentTotals(lines, true)).toEqual({ subtotal: 224655.17, tax: 35944.83, total: 260600, discount: 0 })
  })

  it('adds VAT on top when prices exclude it', () => {
    const line = lineAmounts({ quantity: 10, unitPrice: 120, discountPercent: 5, taxRate: 16 }, false)
    expect(line).toMatchObject({ discount: 60, subtotal: 1140, tax: 182.4, total: 1322.4 })
  })
})

describe('SalesDocumentDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    saveTokens({ access_token: 'a', refresh_token: 'r' })
    authApi.me.mockResolvedValue({
      id: 'me',
      full_name: 'Sales Person',
      email: 's@x.com',
      roles: [],
      permissions: ['sales.view', 'sales.update'],
      is_super_admin: false,
    })
  })

  const quotation = {
    id: 'q1',
    quote_number: 'QUO-2026-00001',
    customer: { id: 'c1', code: 'KCASH', name: 'Lusaka Water' },
    quote_date: '2026-09-16',
    valid_until: '2026-10-16',
    customer_reference: 'LWSC-7781',
    prices_include_tax: true,
    notes: null,
    lines: [
      {
        id: 'l1',
        line_no: 1,
        product: { id: 'p1', sku: 'CHINT', name: 'Contactor 12A', unit: 'pcs' },
        description: 'Contactor running current 12A 3phase',
        quantity: '15.000',
        unit_price: '450.00',
        discount_percent: '0.00',
        tax_rate: '16.00',
      },
    ],
  }

  it('shows the running totals and saves the edited quotation', { timeout: 30_000 }, async () => {
    quotationsApi.update.mockResolvedValue(quotation)
    renderWithProviders(<SalesDocumentDrawer kind="quotation" open document={quotation} onClose={() => {}} />)

    expect(await screen.findByText('ZMW 6,750.00')).toBeInTheDocument() // total incl VAT
    expect(screen.getByText('ZMW 931.03')).toBeInTheDocument() // VAT extracted
    expect(screen.getByText('Price (incl VAT)')).toBeInTheDocument()

    await userEvent.setup().click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(quotationsApi.update).toHaveBeenCalled())
    const [id, body] = quotationsApi.update.mock.calls[0]
    expect(id).toBe('q1')
    expect(body).toMatchObject({
      customer_id: 'c1',
      quote_date: '2026-09-16',
      valid_until: '2026-10-16',
      customer_reference: 'LWSC-7781',
      prices_include_tax: true,
      lines: [
        {
          product_id: 'p1',
          description: 'Contactor running current 12A 3phase',
          quantity: '15',
          unit_price: '450',
          discount_percent: '0',
          tax_rate: '16',
        },
      ],
    })
    expect(body).not.toHaveProperty('warehouse_id') // quotations have no warehouse
  })
})
