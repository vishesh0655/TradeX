import unittest
from decimal import Decimal

from app.schemas import PortfolioOut


class ApiContractTests(unittest.TestCase):
    def test_portfolio_response_exposes_service_total_value(self):
        portfolio = PortfolioOut(
            holdings=[],
            cash_balance=Decimal("1000.00"),
            reserved_cash=Decimal("100.00"),
            available_cash=Decimal("900.00"),
            market_value=Decimal("250.00"),
            invested_value=Decimal("200.00"),
            portfolio_value=Decimal("1250.00"),
            realized_pnl=Decimal("10.00"),
            unrealized_pnl=Decimal("50.00"),
            total_pnl=Decimal("60.00"),
        )
        self.assertEqual(portfolio.portfolio_value, Decimal("1250.00"))


if __name__ == "__main__":
    unittest.main()
