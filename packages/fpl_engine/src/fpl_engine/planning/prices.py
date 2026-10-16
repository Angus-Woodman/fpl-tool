from __future__ import annotations

from fpl_engine.planning.models import require_integer


def selling_price_tenths(purchase_price_tenths: int, market_price_tenths: int) -> int:
    require_integer(purchase_price_tenths, "Purchase price", 1)
    require_integer(market_price_tenths, "Market price", 1)
    if market_price_tenths <= purchase_price_tenths:
        return market_price_tenths
    return purchase_price_tenths + (market_price_tenths - purchase_price_tenths) // 2
