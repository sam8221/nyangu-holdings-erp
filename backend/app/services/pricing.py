"""Line and document totals for tax-exclusive and tax-inclusive prices.

Tax-exclusive: price excludes VAT; each line's VAT = net x rate, rounded to the cent.
Tax-inclusive: price already includes VAT (how Nyangu quotes); VAT is extracted as
total x rate / (100 + rate). On the document, VAT is extracted once per rate from the combined
total, so the totals match the usual printed format (e.g. 260,600.00 incl -> 35,944.83 VAT).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from app.utils.money import HUNDRED, ZERO, money, percent_of


@dataclass(frozen=True)
class LineAmounts:
    discount_amount: Decimal
    subtotal: Decimal  # excluding VAT, after discount
    tax: Decimal
    total: Decimal  # including VAT
    tax_rate: Decimal = ZERO
    inclusive: bool = False


def extract_tax(amount_incl: Decimal, rate: Decimal) -> Decimal:
    """VAT contained in a tax-inclusive amount."""
    if not rate:
        return ZERO
    return money(amount_incl * rate / (HUNDRED + rate))


def line_amounts(
    quantity: Decimal,
    unit_price: Decimal,
    discount_percent: Decimal = ZERO,
    tax_rate: Decimal = ZERO,
    *,
    inclusive: bool = False,
) -> LineAmounts:
    gross = money(quantity * unit_price)
    discount = percent_of(gross, discount_percent)
    net = gross - discount
    if inclusive:
        tax = extract_tax(net, tax_rate)
        return LineAmounts(discount, net - tax, tax, net, tax_rate, True)
    tax = percent_of(net, tax_rate)
    return LineAmounts(discount, net, tax, net + tax, tax_rate, False)


@dataclass(frozen=True)
class DocumentTotals:
    subtotal: Decimal  # excluding VAT
    discount_total: Decimal
    tax_total: Decimal
    total: Decimal  # including VAT


def document_totals(lines: Iterable[LineAmounts], *, inclusive: bool = False) -> DocumentTotals:
    lines = list(lines)
    discount = sum((ln.discount_amount for ln in lines), ZERO)
    if inclusive:
        per_rate: dict[Decimal, Decimal] = defaultdict(lambda: ZERO)
        for ln in lines:
            per_rate[ln.tax_rate] += ln.total
        total = sum(per_rate.values(), ZERO)
        tax = sum((extract_tax(amount, rate) for rate, amount in per_rate.items()), ZERO)
        return DocumentTotals(total - tax, discount, tax, total)
    subtotal = sum((ln.subtotal for ln in lines), ZERO)
    tax = sum((ln.tax for ln in lines), ZERO)
    return DocumentTotals(subtotal, discount, tax, subtotal + tax)
