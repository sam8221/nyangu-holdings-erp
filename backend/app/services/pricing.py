"""Line and document totals. One rounding rule everywhere: each line is rounded to the cent."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from app.utils.money import ZERO, money, percent_of


@dataclass(frozen=True)
class LineAmounts:
    discount_amount: Decimal
    subtotal: Decimal  # after discount, before tax
    tax: Decimal
    total: Decimal


def line_amounts(
    quantity: Decimal,
    unit_price: Decimal,
    discount_percent: Decimal = ZERO,
    tax_rate: Decimal = ZERO,
) -> LineAmounts:
    gross = money(quantity * unit_price)
    discount = percent_of(gross, discount_percent)
    subtotal = gross - discount
    tax = percent_of(subtotal, tax_rate)
    return LineAmounts(discount, subtotal, tax, subtotal + tax)


@dataclass(frozen=True)
class DocumentTotals:
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    total: Decimal


def document_totals(lines: Iterable[LineAmounts]) -> DocumentTotals:
    lines = list(lines)
    subtotal = sum((ln.subtotal for ln in lines), ZERO)
    discount = sum((ln.discount_amount for ln in lines), ZERO)
    tax = sum((ln.tax for ln in lines), ZERO)
    return DocumentTotals(subtotal, discount, tax, subtotal + tax)
