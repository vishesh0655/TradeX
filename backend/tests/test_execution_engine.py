import threading
import unittest
from decimal import Decimal

from app import models
from app.services.execution_adapter import ExecutionFill, PaperExecutionAdapter
from app.services.execution_engine import PaperExecutionEngine
from app.services.fill_processor import DuplicateExecution, FillProcessingError


class FakeQuery:
    def __init__(self, db, subject):
        self.db = db
        self.subject = subject

    def filter(self, *args):
        return self

    def with_for_update(self):
        return self

    def first(self):
        if self.subject is models.Execution:
            return self.db.existing_execution
        if self.subject is models.Holding:
            return self.db.holding
        return None


class RecordingSession:
    def __init__(self):
        self.added = []
        self.deleted = []
        self.holding = None
        self.existing_execution = None
        self.rollback_count = 0

    def add(self, item):
        self.added.append(item)
        if isinstance(item, models.Holding):
            self.holding = item

    def delete(self, item):
        self.deleted.append(item)

    def query(self, subject):
        return FakeQuery(self, subject)

    @property
    def new(self):
        return self.added

    def flush(self):
        pass

    def rollback(self):
        self.rollback_count += 1


class ScriptedPaperAdapter:
    venue = "PAPER"

    def __init__(self, fills):
        self.fills = fills

    def create_fills(self, *, order, quote):
        return self.fills


def make_context(side="BUY", quantity=100, *, price=Decimal("30.00")):
    order = models.Order(
        id=11,
        user_id=3,
        stock_id=7,
        side=side,
        order_type="MARKET",
        status="OPEN",
        quantity=quantity,
        filled_quantity=0,
        average_fill_price=None,
        updated_at=None,
    )
    stock = models.Stock(id=7, symbol="TCS", current_price=price)
    wallet = models.Wallet(
        id=8, user_id=3, balance=Decimal("10000.00"), reserved_cash=Decimal("0.00")
    )
    if side == "BUY":
        reservation = models.OrderReservation(
            id=21, order_id=11, user_id=3, stock_id=7, side="BUY",
            reserved_cash=price * quantity, reserved_quantity=0,
            unit_price=price, state="ACTIVE",
        )
        wallet.reserved_cash = price * quantity
        holding = None
    else:
        reservation = models.OrderReservation(
            id=21, order_id=11, user_id=3, stock_id=7, side="SELL",
            reserved_cash=Decimal("0.00"), reserved_quantity=quantity,
            unit_price=None, state="ACTIVE",
        )
        holding = models.Holding(
            id=31, user_id=3, stock_id=7, quantity=quantity,
            reserved_quantity=quantity, average_buy_price=Decimal("20.00"),
        )
    return order, stock, wallet, holding, reservation


def fill(ref, quantity, price):
    return ExecutionFill(ref, quantity, Decimal(price))


def execute(context, fills, db=None):
    order, stock, wallet, holding, reservation = context
    db = db or RecordingSession()
    engine = PaperExecutionEngine(adapter=ScriptedPaperAdapter(fills))
    engine.execute_market(
        db, order=order, stock=stock, wallet=wallet,
        holding=holding, reservation=reservation,
    )
    return db, order, stock, wallet, db.holding or holding, reservation


class PaperExecutionEngineTests(unittest.TestCase):
    def test_full_buy_fill_settles_cash_holding_and_ledger(self):
        result = execute(make_context(), [fill("buy-1", 100, "30.00")])
        db, order, _, wallet, holding, reservation = result
        self.assertEqual(order.status, "FILLED")
        self.assertEqual(order.filled_quantity, 100)
        self.assertEqual(order.remaining_quantity, 0)
        self.assertEqual(wallet.balance, Decimal("7000.00"))
        self.assertEqual(wallet.reserved_cash, Decimal("0.00"))
        self.assertEqual(holding.quantity, 100)
        self.assertEqual(reservation.state, "SETTLED")
        self.assertTrue(any(isinstance(item, models.WalletTransaction) for item in db.added))

    def test_full_sell_fill_settles_shares_and_virtual_cash(self):
        result = execute(
            make_context("SELL"), [fill("sell-1", 100, "30.00")]
        )
        db, order, _, wallet, holding, reservation = result
        self.assertEqual(order.status, "FILLED")
        self.assertEqual(wallet.balance, Decimal("13000.00"))
        self.assertEqual(holding.quantity, 0)
        self.assertEqual(holding.reserved_quantity, 0)
        self.assertEqual(reservation.state, "SETTLED")
        self.assertIn(holding, db.deleted)

    def test_partial_buy_fill_updates_open_order_and_reserves_remainder(self):
        context = make_context()
        result = execute(context, [fill("buy-part", 30, "30.00")])
        _, order, _, wallet, holding, reservation = result
        self.assertEqual(order.status, "PARTIALLY_FILLED")
        self.assertEqual(order.filled_quantity, 30)
        self.assertEqual(order.remaining_quantity, 70)
        self.assertEqual(wallet.balance, Decimal("9100.00"))
        self.assertEqual(wallet.reserved_cash, Decimal("2100.00"))
        self.assertEqual(holding.quantity, 30)
        self.assertEqual(reservation.reserved_cash, Decimal("2100.00"))

    def test_partial_sell_fill_reduces_reserved_and_total_shares(self):
        context = make_context("SELL")
        result = execute(context, [fill("sell-part", 30, "30.00")])
        _, order, _, wallet, holding, reservation = result
        self.assertEqual(order.status, "PARTIALLY_FILLED")
        self.assertEqual(order.remaining_quantity, 70)
        self.assertEqual(wallet.balance, Decimal("10900.00"))
        self.assertEqual(holding.quantity, 70)
        self.assertEqual(holding.reserved_quantity, 70)
        self.assertEqual(reservation.reserved_quantity, 70)

    def test_multiple_executions_compute_weighted_average_price(self):
        context = make_context(price=Decimal("30.00"))
        fills = [
            fill("multi-1", 30, "10.00"),
            fill("multi-2", 20, "20.00"),
            fill("multi-3", 50, "30.00"),
        ]
        db, order, _, wallet, holding, reservation = execute(context, fills)
        self.assertEqual(order.status, "FILLED")
        self.assertEqual(order.average_fill_price, Decimal("22.00"))
        self.assertEqual(order.filled_quantity, 100)
        self.assertEqual(holding.quantity, 100)
        self.assertEqual(wallet.reserved_cash, Decimal("0.00"))
        self.assertEqual(reservation.reserved_cash, Decimal("0.00"))
        executions = [item for item in db.added if isinstance(item, models.Execution)]
        self.assertEqual(len(executions), 3)

    def test_execution_records_have_unique_references(self):
        db, *_ = execute(make_context(), [fill("unique-exec", 100, "30.00")])
        execution = next(item for item in db.added if isinstance(item, models.Execution))
        self.assertEqual(execution.execution_ref, "unique-exec")
        self.assertEqual(execution.quantity, 100)

    def test_duplicate_execution_reference_is_rejected(self):
        db = RecordingSession()
        db.existing_execution = models.Execution(
            id=1, order_id=11, execution_ref="duplicate", quantity=1,
            execution_price=Decimal("30.00"),
        )
        context = make_context()
        order, stock, wallet, holding, reservation = context
        engine = PaperExecutionEngine(adapter=ScriptedPaperAdapter([fill("duplicate", 100, "30.00")]))
        with self.assertRaises(DuplicateExecution):
            engine.execute_market(
                db, order=order, stock=stock, wallet=wallet,
                holding=holding, reservation=reservation,
            )
        self.assertEqual(db.rollback_count, 1)

    def test_failed_multi_fill_settlement_rolls_back_entire_order_transaction(self):
        db = RecordingSession()
        context = make_context()
        order, stock, wallet, holding, reservation = context
        adapter = ScriptedPaperAdapter([
            fill("rollback-1", 10, "20.00"),
            fill("rollback-2", 10, "40.00"),  # exceeds the remaining reserved cap
        ])
        with self.assertRaises(FillProcessingError):
            PaperExecutionEngine(adapter=adapter).execute_market(
                db, order=order, stock=stock, wallet=wallet,
                holding=holding, reservation=reservation,
            )
        self.assertEqual(db.rollback_count, 1)

    def test_cancelled_order_cannot_be_settled(self):
        context = make_context()
        order, stock, wallet, holding, reservation = context
        order.status = "CANCELLED"
        db = RecordingSession()
        with self.assertRaises(FillProcessingError):
            PaperExecutionEngine(adapter=ScriptedPaperAdapter([fill("cancelled", 1, "30.00")])).execute_market(
                db, order=order, stock=stock, wallet=wallet,
                holding=holding, reservation=reservation,
            )
        self.assertEqual(db.rollback_count, 1)

    def test_concurrent_settlements_cannot_overfill_order(self):
        context = make_context()
        order, stock, wallet, holding, reservation = context
        db = RecordingSession()
        engine = PaperExecutionEngine(adapter=PaperExecutionAdapter())
        serialization_lock = threading.Lock()  # mirrors wallet/order FOR UPDATE
        barrier = threading.Barrier(2)
        results = []

        def settle(index):
            barrier.wait()
            with serialization_lock:
                try:
                    engine.fill_processor.process_fill(
                        db, order=order, stock=stock, wallet=wallet,
                        holding=holding, reservation=reservation,
                        fill=fill(f"concurrent-{index}", 60, "30.00"),
                    )
                    results.append("filled")
                except FillProcessingError:
                    results.append("rejected")

        threads = [threading.Thread(target=settle, args=(i,)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)
        self.assertCountEqual(results, ["filled", "rejected"])
        self.assertEqual(order.filled_quantity, 60)
        self.assertEqual(order.remaining_quantity, 40)

    def test_default_adapter_uses_current_database_price_without_price_generation(self):
        order, stock, *_ = make_context()
        from app.services.market_data import StoredPriceProvider

        quote = StoredPriceProvider().get_quote(stock)
        fills = PaperExecutionAdapter().create_fills(order=order, quote=quote)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].execution_price, Decimal("30.00"))
        self.assertEqual(fills[0].quantity, order.quantity)


if __name__ == "__main__":
    unittest.main()
