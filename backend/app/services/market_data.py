"""Price-provider contract for the paper market.

The active provider reads the internal Stock price. A future virtual market
simulator can implement this contract without changing trading/accounting rules.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol

from app import models


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    price: Decimal
    observed_at: datetime
    source: str


class MarketPriceProvider(Protocol):
    def get_quote(self, instrument: models.Stock) -> MarketQuote: ...


class StoredPriceProvider:
    """Expose a stock's stored internal price as a validated paper quote."""

    def get_quote(self, instrument: models.Stock) -> MarketQuote:
        price = Decimal(instrument.current_price)
        if not price.is_finite() or price <= 0:
            raise ValueError("Paper market price must be positive")
        return MarketQuote(
            symbol=instrument.symbol,
            price=price,
            observed_at=getattr(instrument, "updated_at", None)
            or datetime.now(timezone.utc),
            source="TRADEX_STORED",
        )


market_price_provider: MarketPriceProvider = StoredPriceProvider()
