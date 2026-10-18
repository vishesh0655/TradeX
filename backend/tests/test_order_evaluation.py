import threading
import unittest
from decimal import Decimal

from app import models
from app.services.execution_adapter import ExecutionFill, PaperExecutionAdapter
from app.services.execution_engine import PaperExecutionEngine
from app.services.order_evaluation import OrderEvaluationService


class FakeQuery:
    def __init__(self, db, subjects):
        self.db = db
        self.subjects = subjects
        self.lock_requested = False

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def with_for_update(self, *args, **kwargs):
        self.lock_requested = True
        return self

    def first(self):
        model = self.subjects[0] if len(self.subjects) == 1 else None
        if model is models.Stock:
            return self.db.stock
        if model is models.Wallet:
            if self.lock_requested:
                self.db.wallet_lock.acquire()
                self.db.local.wallet_locked = True
            return self.db.wallet
        if model is models.Order:
            return self.db.order
        if model is models.Holding:
            return self.db.holding
        if model is models.OrderReservation:
            return self.db.reservation
        if model is models.Execution:
            return self.db.existing_execution
        return None

    def all(self):
        if self.subjects and self.subjects[0] is models.Order.id:
            if self.db.order.status in {"OPEN", "PARTIALLY_FILLED"}:
                return [(self.db.order.id, self.db.order.user_id)]
        return []


class FakeSession:
    def __init__(self, order, stock, wallet, holding, reservation):
        self.order = order
        self.stock = stock
        self.wallet = wallet
        self.holding = holding
        self.reservation = reservation
        self.added = []
        self.deleted = []
        self.existing_execution = None
        self.wallet_lock = threading.Lock()
        self.local = threading.local()
        self.commit_count = 0
        self.rollback_count = 0

    def query(self, *subjects):
        return FakeQuery(self, subjects)

    def add(self, item):
        self.added.append(item)
        if isinstance(item, models.Holding):
            self.holding = item

    def delete(self, item):
        self.deleted.append(item)

    def flush(self):
        pass

    def _unlock(self):
        if getattr(self.local, "wallet_locked", False):
            self.local.wallet_locked = False
            self.wallet_lock.release()

    def commit(self):
        self.commit_count += 1
        self._unlock()

    def rollback(self):
        self.rollback_count += 1
        self._unlock()


def make_session(
    *, side="BUY", order_type="LIMIT", quantity=2,
    current_price=Decimal("100.00"), limit_price=Decimal("100.00"),
    stop_price=None, status="OPEN", stop_triggered=False,
    balance=Decimal("10000.00"), holding_quantity=10,
    reservation=True, engine=None,
):
    stock = models.Stock(id=7, symbol="TCS", is_active=True, current_price=current_price)
    order = models.Order(
        id=11, user_id=3, stock_id=7, side=side, order_type=order_type,
        status=status, quantity=quantity, filled_quantity=0,
        limit_price=limit_price if order_type in {"LIMIT", "STOP_LIMIT"} else None,
        stop_price=stop_price, stop_triggered=stop_triggered,
        triggered_at=None, average_fill_price=None, updated_at=None,
    )
    wallet = models.Wallet(id=8, user_id=3, balance=balance, reserved_cash=Decimal("0.00"))
    if side == "BUY":
        unit_price = (
            current_price if order_type == "MARKET" else
            limit_price if order_type in {"LIMIT", "STOP_LIMIT"} else stop_price
        )
        reserve_cash = Decimal(unit_price) * quantity if reservation else Decimal("0.00")
        wallet.reserved_cash = reserve_cash
        holding = None
    else:
        holding = models.Holding(
            id=31, user_id=3, stock_id=7, quantity=holding_quantity,
            reserved_quantity=quantity if reservation else 0,
            average_buy_price=Decimal("80.00"),
        )
        reserve_cash = Decimal("0.00")
        unit_price = None
    order_reservation = None
    if reservation:
        order_reservation = models.OrderReservation(
            id=21, order_id=11, user_id=3, stock_id=7, side=side,
            reserved_cash=reserve_cash,
            reserved_quantity=quantity if side == "SELL" else 0,
            unit_price=unit_price,
            state="ACTIVE",
        )
    session = FakeSession(order, stock, wallet, holding, order_reservation)
    if engine is not None:
        session.engine = engine
    return session


class FixedAdapter:
    venue = "PAPER"

    def __init__(self, fills):
        self.fills = fills

    def create_fills(self, *, order, quote):
        return self.fills


class OrderEvaluationTests(unittest.TestCase):
    def service(self, session, engine=None):
        return OrderEvaluationService(engine or PaperExecutionEngine())

    def evaluate(self, session, price):
        return self.service(session).evaluate_open_orders(
            session, stock_symbol="tcs", current_price=price
        )

    def test_limit_buy_triggers_at_or_below_limit(self):
        session = make_session(limit_price=Decimal("100.00"))
        report = self.evaluate(session, Decimal("99.00"))
        self.assertEqual(session.order.status, "FILLED")
        self.assertEqual(report.orders_filled, 1)

    def test_limit_sell_triggers_at_or_above_limit(self):
        session = make_session(
            side="SELL", limit_price=Decimal("100.00"), current_price=Decimal("101.00")
        )
        report = self.evaluate(session, Decimal("101.00"))
        self.assertEqual(session.order.status, "FILLED")
        self.assertEqual(report.orders_filled, 1)

    def test_stop_buy_triggers_at_or_above_stop(self):
        session = make_session(
            order_type="STOP", stop_price=Decimal("100.00"),
            current_price=Decimal("100.00"), quantity=2,
        )
        report = self.evaluate(session, Decimal("100.00"))
        self.assertTrue(session.order.stop_triggered)
        self.assertIsNotNone(session.order.triggered_at)
        self.assertEqual(session.order.status, "FILLED")
        self.assertEqual(report.stop_orders_triggered, 1)

    def test_stop_sell_triggers_at_or_below_stop(self):
        session = make_session(
            side="SELL", order_type="STOP", stop_price=Decimal("100.00"),
            current_price=Decimal("99.00"),
        )
        report = self.evaluate(session, Decimal("99.00"))
        self.assertTrue(session.order.stop_triggered)
        self.assertEqual(session.order.status, "FILLED")
        self.assertEqual(report.stop_orders_triggered, 1)

    def test_stop_limit_triggers_once_then_waits_for_limit_eligibility(self):
        session = make_session(
            order_type="STOP_LIMIT", stop_price=Decimal("100.00"),
            limit_price=Decimal("105.00"), current_price=Decimal("110.00"),
        )
        first = self.evaluate(session, Decimal("110.00"))
        self.assertTrue(session.order.stop_triggered)
        self.assertEqual(session.order.status, "OPEN")
        self.assertEqual(first.stop_orders_triggered, 1)
        self.assertFalse(any(isinstance(row, models.Execution) for row in session.added))

        second = self.evaluate(session, Decimal("104.00"))
        self.assertEqual(second.stop_orders_triggered, 0)
        self.assertEqual(session.order.status, "FILLED")
        self.assertEqual(session.order.filled_quantity, 2)
        trigger_events = [e for e in session.added if getattr(e, "event_type", None) == "STOP_TRIGGERED"]
        self.assertEqual(len(trigger_events), 1)

    def test_non_triggering_orders_remain_open(self):
        session = make_session(limit_price=Decimal("90.00"))
        report = self.evaluate(session, Decimal("100.00"))
        self.assertEqual(session.order.status, "OPEN")
        self.assertEqual(report.orders_filled, 0)
        self.assertFalse(any(isinstance(row, models.Execution) for row in session.added))

    def test_filled_and_cancelled_orders_are_not_evaluated(self):
        for status in ("FILLED", "CANCELLED", "EXPIRED"):
            with self.subTest(status=status):
                session = make_session(status=status)
                report = self.evaluate(session, Decimal("90.00"))
                self.assertEqual(report.orders_evaluated, 0)
                self.assertFalse(any(isinstance(row, models.Execution) for row in session.added))

    def test_partial_fills_keep_order_open_and_reservation_active(self):
        session = make_session(quantity=5, limit_price=Decimal("100.00"))
        engine = PaperExecutionEngine(adapter=PaperExecutionAdapter(max_fill_quantity=2))
        self.service(session, engine).evaluate_open_orders(
            session, stock_symbol="TCS", current_price=Decimal("95.00")
        )
        self.assertEqual(session.order.status, "PARTIALLY_FILLED")
        self.assertEqual(session.order.filled_quantity, 2)
        self.assertEqual(session.order.remaining_quantity, 3)
        self.assertEqual(session.reservation.reserved_cash, Decimal("300.00"))
        self.assertEqual(session.wallet.reserved_cash, Decimal("300.00"))

    def test_duplicate_execution_rolls_back_evaluation(self):
        session = make_session()
        existing = models.Execution(
            id=1, order_id=11, execution_ref="PAPER-fixed", quantity=1,
            execution_price=Decimal("100.00"),
        )
        session.existing_execution = existing
        engine = PaperExecutionEngine(adapter=FixedAdapter([
            ExecutionFill("PAPER-fixed", 2, Decimal("100.00"))
        ]))
        with self.assertRaises(ValueError):
            self.service(session, engine).evaluate_open_orders(
                session, stock_symbol="TCS", current_price=Decimal("100.00")
            )
        self.assertGreaterEqual(session.rollback_count, 1)

    def test_stop_buy_reservation_is_resized_to_trigger_price(self):
        session = make_session(
            order_type="STOP", stop_price=Decimal("100.00"),
            current_price=Decimal("105.00"), quantity=2,
        )
        self.evaluate(session, Decimal("105.00"))
        self.assertEqual(session.reservation.state, "SETTLED")
        self.assertEqual(session.wallet.balance, Decimal("9790.00"))
        self.assertEqual(session.wallet.reserved_cash, Decimal("0.00"))

    def test_concurrent_evaluations_settle_order_only_once(self):
        session = make_session()
        service = self.service(session)
        barrier = threading.Barrier(2)
        errors = []

        def evaluate():
            barrier.wait()
            try:
                service.evaluate_open_orders(
                    session, stock_symbol="TCS", current_price=Decimal("99.00")
                )
            except Exception as exc:  # surfaced to the parent test thread
                errors.append(exc)

        threads = [threading.Thread(target=evaluate) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)
        self.assertEqual(errors, [])
        executions = [row for row in session.added if isinstance(row, models.Execution)]
        self.assertEqual(len(executions), 1)
        self.assertEqual(session.order.status, "FILLED")


if __name__ == "__main__":
    unittest.main()
