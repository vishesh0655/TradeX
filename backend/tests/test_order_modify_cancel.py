import threading
import unittest
from decimal import Decimal
from types import SimpleNamespace

from app import models
from app.services.order_service import OrderService, OrderServiceError


class Query:
    def __init__(self, db, model):
        self.db = db
        self.model = model

    def filter(self, *args):
        return self

    def with_for_update(self):
        if self.model is models.Wallet:
            self.db.lock.acquire()
            self.db.lock_held = True
        return self

    def first(self):
        return self.db.rows.get(self.model)


class FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.added = []
        self.lock = threading.RLock()
        self.lock_held = False
        self.commits = 0
        self.rollbacks = 0

    def query(self, model):
        return Query(self, model)

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1
        self._unlock()

    def rollback(self):
        self.rollbacks += 1
        self._unlock()

    def refresh(self, value):
        return None

    def _unlock(self):
        if self.lock_held:
            self.lock_held = False
            self.lock.release()


def fixture(*, side="BUY", order_type="LIMIT", quantity=5, status="OPEN", owner=11,
            filled=0, triggered=False):
    stock = SimpleNamespace(id=7, symbol="TCS", is_active=True, current_price=Decimal("100.00"))
    wallet = SimpleNamespace(
        id=8, user_id=owner, balance=Decimal("10000.00"), reserved_cash=Decimal("500.00"),
        updated_at=None,
    )
    holding = SimpleNamespace(
        id=9, user_id=owner, stock_id=7, quantity=20, reserved_quantity=5, updated_at=None,
    )
    limit_price = Decimal("100.00") if order_type in {"LIMIT", "STOP_LIMIT"} else None
    stop_price = Decimal("90.00") if order_type in {"STOP", "STOP_LIMIT"} else None
    order = SimpleNamespace(
        id=13, user_id=owner, stock_id=7, side=side, order_type=order_type,
        quantity=quantity, filled_quantity=filled, status=status,
        limit_price=limit_price, stop_price=stop_price,
        stop_triggered=triggered, updated_at=None,
        remaining_quantity=quantity - filled,
    )
    reservation = SimpleNamespace(
        order_id=13, side=side, state="ACTIVE",
        reserved_cash=Decimal("500.00") if side == "BUY" else Decimal("0.00"),
        reserved_quantity=5 if side == "SELL" else 0,
        unit_price=Decimal("100.00") if side == "BUY" else None,
        updated_at=None,
    )
    return FakeDB({
        models.Wallet: wallet,
        models.Order: order,
        models.Stock: stock,
        models.Holding: holding,
        models.OrderReservation: reservation,
    })


class OrderModifyCancelTests(unittest.TestCase):
    def setUp(self):
        self.service = OrderService()

    def test_cancel_open_releases_buy_cash(self):
        db = fixture()
        order = self.service.cancel_order(db, user_id=11, order_id=13)
        self.assertEqual(order.status, "CANCELLED")
        self.assertEqual(db.rows[models.Wallet].reserved_cash, Decimal("0.00"))
        self.assertEqual(db.rows[models.OrderReservation].state, "RELEASED")
        self.assertTrue(any(getattr(e, "event_type", None) == "ORDER_CANCELLED" for e in db.added))
        self.assertTrue(any(
            getattr(e, "event_type", None) == "RESERVATION_RELEASED" for e in db.added
        ))
        self.assertEqual(db.commits, 1)

    def test_cancel_partially_filled_releases_remaining_shares(self):
        db = fixture(side="SELL", status="PARTIALLY_FILLED", filled=2)
        db.rows[models.Holding].quantity = 18
        db.rows[models.Holding].reserved_quantity = 3
        db.rows[models.OrderReservation].reserved_quantity = 3
        db.rows[models.Order].quantity = 5
        order = self.service.cancel_order(db, user_id=11, order_id=13)
        self.assertEqual(order.status, "CANCELLED")
        self.assertEqual(db.rows[models.Holding].reserved_quantity, 0)
        self.assertEqual(db.rows[models.OrderReservation].reserved_quantity, 0)

    def test_cancel_rejects_filled_and_cancelled(self):
        for state in ("FILLED", "CANCELLED", "REJECTED", "EXPIRED"):
            with self.subTest(state=state):
                db = fixture(status=state)
                with self.assertRaises(OrderServiceError) as error:
                    self.service.cancel_order(db, user_id=11, order_id=13)
                self.assertEqual(error.exception.status_code, 409)
                self.assertEqual(db.rows[models.Wallet].reserved_cash, Decimal("500.00"))
                self.assertEqual(db.commits, 0)

    def test_modify_limit_price_resizes_cash_reservation(self):
        db = fixture()
        order = self.service.modify_order(
            db, user_id=11, order_id=13, changes={"limit_price": Decimal("80.00")}
        )
        self.assertEqual(order.limit_price, Decimal("80.00"))
        self.assertEqual(db.rows[models.OrderReservation].reserved_cash, Decimal("400.00"))
        self.assertEqual(db.rows[models.Wallet].reserved_cash, Decimal("400.00"))
        self.assertTrue(any(getattr(e, "event_type", None) == "ORDER_MODIFIED" for e in db.added))

    def test_modify_quantity_resizes_buy_reservation(self):
        db = fixture()
        order = self.service.modify_order(
            db, user_id=11, order_id=13, changes={"quantity": 3}
        )
        self.assertEqual(order.quantity, 3)
        self.assertEqual(db.rows[models.OrderReservation].reserved_cash, Decimal("300.00"))
        self.assertEqual(db.rows[models.Wallet].reserved_cash, Decimal("300.00"))

    def test_increased_quantity_rechecks_available_funds(self):
        db = fixture()
        db.rows[models.Wallet].balance = Decimal("600.00")
        with self.assertRaises(OrderServiceError) as error:
            self.service.modify_order(db, user_id=11, order_id=13, changes={"quantity": 7})
        self.assertIn("Insufficient available cash", error.exception.message)
        self.assertEqual(db.rows[models.Order].quantity, 5)
        self.assertEqual(db.rows[models.Wallet].reserved_cash, Decimal("500.00"))
        self.assertEqual(db.rollbacks, 1)

    def test_sell_quantity_increase_rechecks_available_shares(self):
        db = fixture(side="SELL")
        with self.assertRaises(OrderServiceError) as error:
            self.service.modify_order(db, user_id=11, order_id=13, changes={"quantity": 21})
        self.assertIn("Insufficient available shares", error.exception.message)
        self.assertEqual(db.rows[models.Holding].reserved_quantity, 5)

    def test_reducing_sell_quantity_releases_excess_share_reservation(self):
        db = fixture(side="SELL")
        order = self.service.modify_order(
            db, user_id=11, order_id=13, changes={"quantity": 3}
        )
        self.assertEqual(order.quantity, 3)
        self.assertEqual(db.rows[models.Holding].reserved_quantity, 3)
        self.assertEqual(db.rows[models.OrderReservation].reserved_quantity, 3)

    def test_reject_invalid_fields_prices_and_started_execution(self):
        db = fixture()
        with self.assertRaises(OrderServiceError):
            self.service.modify_order(db, user_id=11, order_id=13, changes={"side": "SELL"})
        db = fixture()
        with self.assertRaises(OrderServiceError):
            self.service.modify_order(db, user_id=11, order_id=13, changes={"limit_price": None})
        db = fixture(status="PARTIALLY_FILLED", filled=1)
        with self.assertRaises(OrderServiceError) as error:
            self.service.modify_order(db, user_id=11, order_id=13, changes={"quantity": 6})
        self.assertEqual(error.exception.status_code, 409)

    def test_order_ownership_is_enforced(self):
        db = fixture(owner=22)
        with self.assertRaises(OrderServiceError) as error:
            self.service.cancel_order(db, user_id=11, order_id=13)
        self.assertEqual(error.exception.status_code, 403)
        db = fixture(owner=22)
        with self.assertRaises(OrderServiceError) as error:
            self.service.modify_order(db, user_id=11, order_id=13, changes={"quantity": 4})
        self.assertEqual(error.exception.status_code, 403)

    def test_concurrent_cancel_and_modify_are_serialized(self):
        db = fixture()
        barrier = threading.Barrier(2)
        outcomes = []

        def cancel():
            barrier.wait()
            try:
                self.service.cancel_order(db, user_id=11, order_id=13)
                outcomes.append("cancelled")
            except OrderServiceError:
                outcomes.append("cancel-rejected")

        def modify():
            barrier.wait()
            try:
                self.service.modify_order(
                    db, user_id=11, order_id=13, changes={"limit_price": Decimal("80.00")}
                )
                outcomes.append("modified")
            except OrderServiceError:
                outcomes.append("modify-rejected")

        threads = [threading.Thread(target=cancel), threading.Thread(target=modify)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertIn("cancelled", outcomes)
        self.assertEqual(db.rows[models.Wallet].reserved_cash, Decimal("0.00"))
        self.assertEqual(db.rows[models.OrderReservation].state, "RELEASED")


if __name__ == "__main__":
    unittest.main()
