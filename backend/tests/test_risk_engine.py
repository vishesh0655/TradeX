import threading
import unittest
from decimal import Decimal
from types import SimpleNamespace

from app.services.risk_engine import RiskEngine, RiskRejected


class RecordingDB:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)


def order(side="BUY", qty=1, price=Decimal("80.00"), filled=0):
    return SimpleNamespace(
        id=1, user_id=3, stock_id=7, side=side, order_type="LIMIT",
        quantity=qty, filled_quantity=filled, limit_price=price, stop_price=None,
        remaining_quantity=qty - filled,
    )


class RiskEngineTests(unittest.TestCase):
    def setUp(self):
        self.db = RecordingDB()
        self.stock = SimpleNamespace(id=7, is_active=True, current_price=Decimal("100.00"))
        self.wallet = SimpleNamespace(
            id=8, user_id=3, balance=Decimal("500.00"), reserved_cash=Decimal("0.00")
        )
        self.holding = SimpleNamespace(quantity=8, reserved_quantity=0)

    def test_buy_reservation_reduces_available_cash(self):
        reservation = RiskEngine.reserve_order(
            self.db, order=order(qty=2), stock=self.stock,
            wallet=self.wallet, holding=None,
        )
        self.assertEqual(reservation.reserved_cash, Decimal("160.00"))
        self.assertEqual(self.wallet.balance - self.wallet.reserved_cash, Decimal("340.00"))

    def test_insufficient_funds_rejected_including_existing_reservations(self):
        self.wallet.reserved_cash = Decimal("450.00")
        with self.assertRaises(RiskRejected):
            RiskEngine.reserve_order(
                self.db, order=order(qty=1), stock=self.stock,
                wallet=self.wallet, holding=None,
            )

    def test_sell_reservation_and_insufficient_shares(self):
        reservation = RiskEngine.reserve_order(
            self.db, order=order(side="SELL", qty=5), stock=self.stock,
            wallet=self.wallet, holding=self.holding,
        )
        self.assertEqual(self.holding.reserved_quantity, 5)
        self.assertEqual(self.holding.quantity - self.holding.reserved_quantity, 3)
        with self.assertRaises(RiskRejected):
            RiskEngine.reserve_order(
                self.db, order=order(side="SELL", qty=4), stock=self.stock,
                wallet=self.wallet, holding=self.holding,
            )
        self.assertEqual(reservation.reserved_quantity, 5)

    def test_partial_buy_fill_reduces_cash_reservation(self):
        buy_order = order(qty=4)
        reservation = RiskEngine.reserve_order(
            self.db, order=buy_order, stock=self.stock, wallet=self.wallet, holding=None
        )
        RiskEngine.apply_fill(
            order=buy_order, reservation=reservation, wallet=self.wallet,
            holding=None, quantity=1, execution_price=Decimal("80.00"),
        )
        buy_order.filled_quantity = 1
        self.assertEqual(reservation.reserved_cash, Decimal("240.00"))
        self.assertEqual(self.wallet.reserved_cash, Decimal("240.00"))
        self.assertEqual(self.wallet.balance, Decimal("420.00"))

    def test_partial_sell_fill_reduces_share_reservation(self):
        sell_order = order(side="SELL", qty=4)
        reservation = RiskEngine.reserve_order(
            self.db, order=sell_order, stock=self.stock,
            wallet=self.wallet, holding=self.holding,
        )
        RiskEngine.apply_fill(
            order=sell_order, reservation=reservation, wallet=self.wallet,
            holding=self.holding, quantity=2, execution_price=Decimal("100.00"),
        )
        sell_order.filled_quantity = 2
        self.assertEqual(reservation.reserved_quantity, 2)
        self.assertEqual(self.holding.quantity, 6)
        self.assertEqual(self.holding.reserved_quantity, 2)

    def test_cancel_releases_cash_and_shares(self):
        buy = order(qty=2)
        buy_reservation = RiskEngine.reserve_order(
            self.db, order=buy, stock=self.stock, wallet=self.wallet, holding=None
        )
        RiskEngine.release(reservation=buy_reservation, wallet=self.wallet, holding=None)
        self.assertEqual(self.wallet.reserved_cash, Decimal("0.00"))
        self.assertEqual(buy_reservation.state, "RELEASED")

        sell = order(side="SELL", qty=3)
        sell_reservation = RiskEngine.reserve_order(
            self.db, order=sell, stock=self.stock, wallet=self.wallet, holding=self.holding
        )
        RiskEngine.release(reservation=sell_reservation, wallet=self.wallet, holding=self.holding)
        self.assertEqual(self.holding.reserved_quantity, 0)
        self.assertEqual(sell_reservation.reserved_quantity, 0)

    def test_execution_cannot_exceed_buy_reservation(self):
        buy = order(qty=1, price=Decimal("80.00"))
        reservation = RiskEngine.reserve_order(
            self.db, order=buy, stock=self.stock, wallet=self.wallet, holding=None
        )
        with self.assertRaises(RiskRejected):
            RiskEngine.apply_fill(
                order=buy, reservation=reservation, wallet=self.wallet,
                holding=None, quantity=1, execution_price=Decimal("81.00"),
            )

    def test_simultaneous_buy_checks_serialize_on_wallet(self):
        wallet = SimpleNamespace(
            id=8, user_id=3, balance=Decimal("100.00"), reserved_cash=Decimal("0.00")
        )
        stock = self.stock
        lock = threading.Lock()
        barrier = threading.Barrier(2)
        results = []

        def submit(index):
            candidate = order(qty=1, price=Decimal("80.00"))
            candidate.id = index
            barrier.wait()
            with lock:  # mirrors OrderService's SELECT FOR UPDATE wallet row
                try:
                    RiskEngine.reserve_order(
                        RecordingDB(), order=candidate, stock=stock,
                        wallet=wallet, holding=None,
                    )
                    results.append("accepted")
                except RiskRejected:
                    results.append("rejected")

        threads = [threading.Thread(target=submit, args=(n,)) for n in (1, 2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)
        self.assertCountEqual(results, ["accepted", "rejected"])
        self.assertEqual(wallet.reserved_cash, Decimal("80.00"))

    def test_simultaneous_sell_checks_serialize_on_wallet_and_holding(self):
        wallet = SimpleNamespace(
            id=8, user_id=3, balance=Decimal("100.00"), reserved_cash=Decimal("0.00")
        )
        holding = SimpleNamespace(quantity=1, reserved_quantity=0)
        lock = threading.Lock()
        barrier = threading.Barrier(2)
        results = []

        def submit(index):
            candidate = order(side="SELL", qty=1)
            candidate.id = index
            barrier.wait()
            with lock:
                try:
                    RiskEngine.reserve_order(
                        RecordingDB(), order=candidate, stock=self.stock,
                        wallet=wallet, holding=holding,
                    )
                    results.append("accepted")
                except RiskRejected:
                    results.append("rejected")

        threads = [threading.Thread(target=submit, args=(n,)) for n in (1, 2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)
        self.assertCountEqual(results, ["accepted", "rejected"])
        self.assertEqual(holding.reserved_quantity, 1)


if __name__ == "__main__":
    unittest.main()
