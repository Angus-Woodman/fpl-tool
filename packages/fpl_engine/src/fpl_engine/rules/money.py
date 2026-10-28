from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

from fpl_engine.rules.errors import RuleViolationError

# £10,000m: far beyond any squad, bank or price, so garbage fails fast.
MAX_MONEY_TENTHS = 100_000

# Float noise from a handful of additions is ~1e-13 tenths; real sub-tenth amounts are >= 0.1.
OBSERVED_TOLERANCE_TENTHS = Decimal("1e-9")


def _to_tenths(value: float, *, tolerance: Decimal, label: str) -> int:
    message = f"{label} must be a finite whole number of tenths (multiples of £0.1m)"
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RuleViolationError("invalid_money", message)
    try:
        scaled = Decimal(str(value)) * 10
    except InvalidOperation as error:
        raise RuleViolationError("invalid_money", message) from error
    if not scaled.is_finite():
        raise RuleViolationError("invalid_money", message)
    nearest = scaled.to_integral_value(rounding=ROUND_HALF_EVEN)
    if abs(scaled - nearest) > tolerance:
        raise RuleViolationError("invalid_money", message)
    if abs(nearest) > MAX_MONEY_TENTHS:
        raise RuleViolationError("invalid_money", f"{label} is outside the supported range")
    return int(nearest)


def exact_tenths(value: float, *, label: str = "Money") -> int:
    """Strict: the value must already be a whole number of tenths."""
    return _to_tenths(value, tolerance=Decimal(0), label=label)


def observed_tenths(value: float, *, label: str = "Money") -> int:
    """Repairs float representation noise only; any real sub-tenth amount is rejected."""
    return _to_tenths(value, tolerance=OBSERVED_TOLERANCE_TENTHS, label=label)


def tenths_to_money(tenths: int) -> float:
    """The nearest double to tenths / 10, so its repr is the clean decimal."""
    return tenths / 10
