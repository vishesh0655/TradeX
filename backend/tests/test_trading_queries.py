import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.services.trading_queries import TradingQueryError, TradingQueryService


class QueryResult:
    def __init__(self, result):
        self.result = result

    def filter(self, *args):
        return self

    def first(self):
        return self.result


class TradingQueryServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = TradingQueryService()
        self.db = Mock()

    def test_page_limits_are_bounded(self):
        self.service._validate_page(1, 0)
        self.service._validate_page(100, 10)
        for limit, offset in ((0, 0), (101, 0), (10, -1)):
            with self.subTest(limit=limit, offset=offset), self.assertRaises(TradingQueryError):
                self.service._validate_page(limit, offset)

    def test_reversed_date_range_is_rejected(self):
        from datetime import datetime, timezone

        with self.assertRaises(TradingQueryError):
            self.service._validate_date_range(
                datetime(2026, 10, 2, tzinfo=timezone.utc),
                datetime(2026, 10, 1, tzinfo=timezone.utc),
            )

    def test_order_lookup_distinguishes_missing_and_foreign_orders(self):
        self.db.query.return_value = QueryResult(None)
        with self.assertRaises(TradingQueryError) as missing:
            self.service.get_order(self.db, user_id=2, order_id=90)
        self.assertEqual(missing.exception.status_code, 404)

        self.db.query.return_value = QueryResult(SimpleNamespace(id=90, user_id=1))
        with self.assertRaises(TradingQueryError) as forbidden:
            self.service.get_order(self.db, user_id=2, order_id=90)
        self.assertEqual(forbidden.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
