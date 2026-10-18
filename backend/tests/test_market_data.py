import unittest
from datetime import datetime, timezone
from decimal import Decimal

from app import models
from app.services.execution_adapter import PaperExecutionAdapter
from app.services.market_data import MarketQuote, StoredPriceProvider


class MarketDataTests(unittest.TestCase):
    def test_stored_provider_returns_internal_quote_metadata(self):
        observed_at = datetime(2026, 10, 18, tzinfo=timezone.utc)
        stock = models.Stock(
            id=1,
            symbol="TCS",
            current_price=Decimal("3400.00"),
            updated_at=observed_at,
        )

        quote = StoredPriceProvider().get_quote(stock)

        self.assertEqual(quote.symbol, "TCS")
        self.assertEqual(quote.price, Decimal("3400.00"))
        self.assertEqual(quote.observed_at, observed_at)
        self.assertEqual(quote.source, "TRADEX_STORED")

    def test_execution_adapter_consumes_quote_not_stock_price(self):
        order = models.Order(
            id=1,
            user_id=1,
            stock_id=1,
            side="BUY",
            order_type="MARKET",
            status="OPEN",
            quantity=2,
            filled_quantity=0,
        )
        quote = MarketQuote(
            symbol="TCS",
            price=Decimal("3210.50"),
            observed_at=datetime(2026, 10, 18, tzinfo=timezone.utc),
            source="TEST_PROVIDER",
        )

        fills = PaperExecutionAdapter().create_fills(order=order, quote=quote)

        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].execution_price, Decimal("3210.50"))


if __name__ == "__main__":
    unittest.main()
