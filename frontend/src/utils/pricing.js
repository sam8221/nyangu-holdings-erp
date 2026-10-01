// Display-only estimate of document totals while a form is being filled in.
// Mirrors backend/app/services/pricing.py; the server's figures are the ones that count.

const round2 = (value) => Math.round((value + Number.EPSILON) * 100) / 100

export function lineAmounts({ quantity, unitPrice, discountPercent = 0, taxRate = 0 }, inclusive) {
  const qty = Number(quantity) || 0
  const price = Number(unitPrice) || 0
  const gross = round2(qty * price)
  const discount = round2((gross * (Number(discountPercent) || 0)) / 100)
  const net = round2(gross - discount)
  const rate = Number(taxRate) || 0
  if (inclusive) {
    const tax = rate ? round2((net * rate) / (100 + rate)) : 0
    return { discount, subtotal: round2(net - tax), tax, total: net, rate }
  }
  const tax = round2((net * rate) / 100)
  return { discount, subtotal: net, tax, total: round2(net + tax), rate }
}

export function documentTotals(lines, inclusive) {
  const discount = round2(lines.reduce((sum, l) => sum + l.discount, 0))
  if (inclusive) {
    const byRate = new Map()
    for (const l of lines) byRate.set(l.rate, (byRate.get(l.rate) || 0) + l.total)
    let total = 0
    let tax = 0
    for (const [rate, amount] of byRate) {
      total += amount
      tax += rate ? round2((amount * rate) / (100 + rate)) : 0
    }
    total = round2(total)
    tax = round2(tax)
    return { subtotal: round2(total - tax), tax, total, discount }
  }
  const subtotal = round2(lines.reduce((sum, l) => sum + l.subtotal, 0))
  const tax = round2(lines.reduce((sum, l) => sum + l.tax, 0))
  return { subtotal, tax, total: round2(subtotal + tax), discount }
}
