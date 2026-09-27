"""Decimal helpers for money and quantities. Never use floats for amounts."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0")
CENT = Decimal("0.01")
MILLI = Decimal("0.001")
HUNDRED = Decimal("100")


def money(value: Decimal | int | str) -> Decimal:
    """Round to 2 decimal places, half up (the usual accounting rule)."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def qty(value: Decimal | int | str) -> Decimal:
    """Round a quantity to 3 decimal places."""
    return Decimal(value).quantize(MILLI, rounding=ROUND_HALF_UP)


def percent_of(amount: Decimal, rate: Decimal) -> Decimal:
    return money(amount * rate / HUNDRED)
