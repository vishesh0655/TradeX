import os
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import models
from app.database import get_db
from app.main import app, require_paper_price_update_token
from app.services.order_evaluation import EvaluationReport
from app.services.paper_price_update import (
    PaperPriceUpdateError,
    PaperPriceUpdateService,
)


class FakeQuery:
    def __init__(self, result):
        self.result = result

    def filter(self, *args):
        return self

    def with_for_update(self):
        return self

    def first(self):
        return self.result


class FakeSession:
    def __init__(self, stock):
        self.stock = stock
        self.query_count = 0
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    def query(self, model):
        self.query_count += 1
        if model is not models.Stock:
            raise AssertionError(f"Unexpected model query: {model}")
        return FakeQuery(self.stock)

    def flush(self):
        self.flush_count += 1

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


def make_stock(*, active=True):
    return SimpleNamespace(
        id=7,
        symbol="TCS",
        is_active=active,
        current_price=Decimal("100.00"),
        updated_at=None,
    )


class PaperPriceUpdateServiceTests(unittest.TestCase):
    def test_price_update_evaluates_orders_and_commits_atomically(self):
        db = FakeSession(make_stock())
        evaluator = Mock()
        evaluator.evaluate_open_orders.return_value = EvaluationReport(
            orders_evaluated=2,
            stop_orders_triggered=1,
            orders_filled=1,
        )

        result = PaperPriceUpdateService(evaluator).update_price(
            db, symbol="tcs", price=Decimal("95.00")
        )

        self.assertEqual(result["previous_price"], Decimal("100.00"))
        self.assertEqual(result["price"], Decimal("95.00"))
        self.assertEqual(result["orders_evaluated"], 2)
        self.assertEqual(result["stop_orders_triggered"], 1)
        self.assertEqual(result["orders_filled"], 1)
        evaluator.evaluate_open_orders.assert_called_once_with(
            db,
            stock_symbol="TCS",
            current_price=Decimal("95.00"),
            commit=False,
        )
        self.assertEqual(db.flush_count, 1)
        self.assertEqual(db.commit_count, 1)
        self.assertEqual(db.rollback_count, 0)

    def test_evaluation_failure_rolls_back_price_update(self):
        stock = make_stock()
        db = FakeSession(stock)
        evaluator = Mock()
        evaluator.evaluate_open_orders.side_effect = RuntimeError("fill failed")

        with self.assertRaises(PaperPriceUpdateError) as error:
            PaperPriceUpdateService(evaluator).update_price(
                db, symbol="TCS", price=Decimal("95.00")
            )

        self.assertEqual(error.exception.status_code, 500)
        self.assertEqual(stock.current_price, Decimal("95.00"))
        self.assertEqual(db.commit_count, 0)
        self.assertEqual(db.rollback_count, 1)

    def test_invalid_price_is_rejected_before_database_access(self):
        db = FakeSession(make_stock())
        service = PaperPriceUpdateService(Mock())
        for price in (Decimal("0"), Decimal("95.001"), Decimal("NaN")):
            with self.subTest(price=price):
                with self.assertRaises(PaperPriceUpdateError):
                    service.update_price(db, symbol="TCS", price=price)
        self.assertEqual(db.query_count, 0)

    def test_inactive_instrument_is_rejected(self):
        db = FakeSession(make_stock(active=False))
        with self.assertRaises(PaperPriceUpdateError) as error:
            PaperPriceUpdateService(Mock()).update_price(
                db, symbol="TCS", price=Decimal("95.00")
            )
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(db.rollback_count, 1)


class PaperPriceUpdateApiTests(unittest.TestCase):
    def test_token_dependency_fails_closed_and_compares_configured_secret(self):
        with patch.dict(os.environ, {"TRADEX_PAPER_PRICE_UPDATE_TOKEN": ""}):
            with self.assertRaises(HTTPException) as disabled:
                require_paper_price_update_token(token=None)
            self.assertEqual(disabled.exception.status_code, 503)

        with patch.dict(os.environ, {"TRADEX_PAPER_PRICE_UPDATE_TOKEN": "secret"}):
            with self.assertRaises(HTTPException) as unauthorized:
                require_paper_price_update_token(token="wrong")
            self.assertEqual(unauthorized.exception.status_code, 401)
            self.assertIsNone(require_paper_price_update_token(token="secret"))

    def test_endpoint_requires_token_and_returns_update_report(self):
        previous_override = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = lambda: iter([object()])
        try:
            with TestClient(app) as client:
                with patch.dict(os.environ, {"TRADEX_PAPER_PRICE_UPDATE_TOKEN": ""}):
                    disabled = client.post(
                        "/internal/paper-prices/TCS", json={"price": "95.00"}
                    )
                self.assertEqual(disabled.status_code, 503)

                with patch.dict(os.environ, {"TRADEX_PAPER_PRICE_UPDATE_TOKEN": "secret"}):
                    denied = client.post(
                        "/internal/paper-prices/TCS",
                        json={"price": "95.00"},
                        headers={"X-TradeX-Price-Token": "wrong"},
                    )
                self.assertEqual(denied.status_code, 401)

                report = {
                    "symbol": "TCS",
                    "previous_price": Decimal("100.00"),
                    "price": Decimal("95.00"),
                    "updated_at": datetime.now(timezone.utc),
                    "orders_evaluated": 3,
                    "stop_orders_triggered": 1,
                    "orders_filled": 2,
                    "orders_partially_filled": 0,
                    "orders_rejected": 0,
                }
                with (
                    patch.dict(os.environ, {"TRADEX_PAPER_PRICE_UPDATE_TOKEN": "secret"}),
                    patch("app.main.paper_price_update_service.update_price", return_value=report) as update,
                ):
                    accepted = client.post(
                        "/internal/paper-prices/TCS",
                        json={"price": "95.00"},
                        headers={"X-TradeX-Price-Token": "secret"},
                    )
                self.assertEqual(accepted.status_code, 200, accepted.text)
                self.assertEqual(accepted.json()["orders_filled"], 2)
                update.assert_called_once()
        finally:
            if previous_override is None:
                app.dependency_overrides.pop(get_db, None)
            else:
                app.dependency_overrides[get_db] = previous_override


if __name__ == "__main__":
    unittest.main()
