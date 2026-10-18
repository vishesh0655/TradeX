import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from app.services.order_service import OrderService, OrderServiceError


class FakeQuery:
    def __init__(self, result):
        self.result = result

    def filter(self, *args):
        return self

    def with_for_update(self):
        return self

    def first(self):
        return self.result


def make_stock():
    return SimpleNamespace(id=7, symbol="TCS", is_active=True, current_price=Decimal("100.00"))


def make_wallet():
    return SimpleNamespace(id=8, user_id=3, balance=Decimal("1000.00"), reserved_cash=Decimal("0.00"))


def make_user():
    return SimpleNamespace(id=3, is_active=True)


class OrderServiceTests(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        self.added = []
        self.db.add.side_effect = self.added.append
        self.db.flush = Mock(side_effect=lambda: setattr(self.added[0], "id", 42))
        self.db.refresh = Mock()
        self.db.commit = Mock()
        self.db.rollback = Mock()
        self.order_evaluator = Mock()
        self.service = OrderService(
            execution_engine=Mock(), order_evaluator=self.order_evaluator
        )

    def test_valid_stop_limit_order_is_created_open(self):
        wallet = make_wallet()
        self.db.query.side_effect = [
            FakeQuery(make_stock()),
            FakeQuery(wallet),
            FakeQuery(make_user()),
            FakeQuery(None),
            FakeQuery(None),
        ]

        order = self.service.place_order(
            self.db,
            user_id=3,
            stock_symbol="tcs",
            side="BUY",
            order_type="STOP_LIMIT",
            quantity=2,
            limit_price=Decimal("98.00"),
            stop_price=Decimal("100.00"),
        )

        self.assertEqual(order.status, "OPEN")
        self.assertEqual(order.remaining_quantity, 2)
        self.assertEqual(order.limit_price, Decimal("98.00"))
        self.assertEqual(order.stop_price, Decimal("100.00"))
        self.assertEqual(self.added[3].reserved_cash, Decimal("196.00"))
        self.assertEqual(wallet.reserved_cash, Decimal("196.00"))
        self.order_evaluator.evaluate_open_orders.assert_called_once_with(
            self.db,
            stock_symbol="TCS",
            current_price=Decimal("100.00"),
            order_id=42,
            commit=False,
        )
        self.db.commit.assert_called_once()
        self.service.execution_engine.execute_market.assert_not_called()

    def test_market_buy_keeps_existing_atomic_paper_fill_path(self):
        self.db.query.side_effect = [
            FakeQuery(make_stock()),
            FakeQuery(make_wallet()),
            FakeQuery(make_user()),
            FakeQuery(None),
            FakeQuery(None),
            FakeQuery(None),
        ]
        self.service = OrderService()

        order = self.service.place_order(
            self.db,
            user_id=3,
            stock_symbol="TCS",
            side="BUY",
            order_type="MARKET",
            quantity=2,
        )

        self.assertEqual(order.status, "FILLED")
        self.assertEqual(order.filled_quantity, 2)
        self.assertEqual(order.remaining_quantity, 0)
        self.assertEqual(order.average_fill_price, Decimal("100.00"))
        self.assertEqual(order.stock_id, 7)
        self.order_evaluator.evaluate_open_orders.assert_not_called()
        self.assertEqual(self.added[1].event_type, "ORDER_CREATED")
        self.assertEqual(self.added[2].event_type, "ORDER_OPENED")
        self.assertTrue(any(
            getattr(item, "event_type", None) == "ORDER_FILLED" for item in self.added
        ))
        self.db.commit.assert_called_once()

    def test_same_client_order_id_and_same_request_returns_existing_order(self):
        existing = SimpleNamespace(
            stock=SimpleNamespace(symbol="TCS"),
            side="BUY",
            order_type="LIMIT",
            quantity=2,
            limit_price=Decimal("98.00"),
            stop_price=None,
        )
        self.db.query.side_effect = [
            FakeQuery(make_stock()), FakeQuery(make_wallet()), FakeQuery(make_user()),
            FakeQuery(existing),
        ]

        result = self.service.place_order(
            self.db,
            user_id=3,
            stock_symbol="TCS",
            side="BUY",
            order_type="LIMIT",
            quantity=2,
            limit_price=Decimal("98.00"),
            client_order_id="client-123",
        )

        self.assertIs(result, existing)
        self.db.commit.assert_not_called()
        self.db.rollback.assert_called_once()
        self.db.add.assert_not_called()

    def test_reusing_client_order_id_for_different_request_conflicts(self):
        existing = SimpleNamespace(
            stock=SimpleNamespace(symbol="TCS"),
            side="BUY",
            order_type="LIMIT",
            quantity=2,
            limit_price=Decimal("98.00"),
            stop_price=None,
        )
        self.db.query.side_effect = [
            FakeQuery(make_stock()), FakeQuery(make_wallet()), FakeQuery(make_user()),
            FakeQuery(existing),
        ]

        with self.assertRaises(OrderServiceError) as context:
            self.service.place_order(
                self.db,
                user_id=3,
                stock_symbol="TCS",
                side="BUY",
                order_type="LIMIT",
                quantity=3,
                limit_price=Decimal("98.00"),
                client_order_id="client-123",
            )

        self.assertEqual(context.exception.status_code, 409)
        self.db.rollback.assert_called_once()

    def test_invalid_service_terms_do_not_query_database(self):
        with self.assertRaises(OrderServiceError):
            self.service.place_order(
                self.db,
                user_id=3,
                stock_symbol="TCS",
                side="BUY",
                order_type="LIMIT",
                quantity=1,
            )
        self.db.query.assert_not_called()

    def test_insufficient_cash_rolls_back_order_and_reservation(self):
        wallet = SimpleNamespace(
            id=8, user_id=3, balance=Decimal("100.00"), reserved_cash=Decimal("0.00")
        )
        self.db.query.side_effect = [
            FakeQuery(make_stock()), FakeQuery(wallet), FakeQuery(make_user()),
            FakeQuery(None), FakeQuery(None),
        ]
        with self.assertRaises(OrderServiceError) as context:
            self.service.place_order(
                self.db, user_id=3, stock_symbol="TCS", side="BUY",
                order_type="LIMIT", quantity=2, limit_price=Decimal("80.00"),
            )
        self.assertIn("Insufficient available cash", context.exception.message)
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()
        self.assertEqual(wallet.reserved_cash, Decimal("0.00"))
