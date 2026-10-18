import unittest
from decimal import Decimal
from types import SimpleNamespace

from app import models
from app.services.accounting_service import AccountingService
from app.services.execution_adapter import ExecutionFill
from app.services.fee_engine import FeeConfig, FeeEngine
from app.services.fill_processor import FillProcessor
from app.services.portfolio_valuation import PortfolioValuationService
from app.services.risk_engine import RiskEngine


class RecordingSession:
    def __init__(self):
        self.added = []
        self.holding = None
        self.deleted = []
        self.rollback_count = 0

    def query(self, subject):
        return FakeQuery(self, subject)

    def add(self, value):
        self.added.append(value)
        if isinstance(value, models.Holding):
            self.holding = value

    def delete(self, value):
        self.deleted.append(value)

    def flush(self):
        return None

    def rollback(self):
        self.rollback_count += 1


class FakeQuery:
    def __init__(self, db, subject):
        self.db = db
        self.subject = subject

    def filter(self, *args):
        return self

    def first(self):
        if self.subject is models.Execution:
            return None
        if self.subject is models.Holding:
            return self.db.holding
        return None


def buy_context(*, quantity, unit_price, fees=Decimal("0.00")):
    gross_reserve = unit_price * quantity
    wallet = models.Wallet(
        id=8, user_id=3, balance=Decimal("10000.00"),
        reserved_cash=gross_reserve + fees,
    )
    order = models.Order(
        id=11, user_id=3, stock_id=7, side="BUY", order_type="MARKET",
        status="OPEN", quantity=quantity, filled_quantity=0,
        average_fill_price=None, updated_at=None,
    )
    stock = models.Stock(id=7, symbol="TCS", company_name="TCS", current_price=unit_price)
    reservation = models.OrderReservation(
        id=21, order_id=11, user_id=3, stock_id=7, side="BUY",
        reserved_cash=gross_reserve + fees, reserved_quantity=0,
        unit_price=unit_price, state="ACTIVE",
    )
    return order, stock, wallet, None, reservation


def sell_context(*, quantity, unit_price, holding_quantity=None, cost_basis=None):
    holding_quantity = quantity if holding_quantity is None else holding_quantity
    cost_basis = Decimal("20.00") * holding_quantity if cost_basis is None else Decimal(cost_basis)
    holding = models.Holding(
        id=31, user_id=3, stock_id=7, quantity=holding_quantity,
        reserved_quantity=quantity, average_buy_price=(cost_basis / holding_quantity),
        cost_basis=cost_basis,
    )
    wallet = models.Wallet(
        id=8, user_id=3, balance=Decimal("10000.00"), reserved_cash=Decimal("0.00")
    )
    order = models.Order(
        id=12, user_id=3, stock_id=7, side="SELL", order_type="MARKET",
        status="OPEN", quantity=quantity, filled_quantity=0,
        average_fill_price=None, updated_at=None,
    )
    stock = models.Stock(id=7, symbol="TCS", company_name="TCS", current_price=unit_price)
    reservation = models.OrderReservation(
        id=22, order_id=12, user_id=3, stock_id=7, side="SELL",
        reserved_cash=Decimal("0.00"), reserved_quantity=quantity,
        unit_price=None, state="ACTIVE",
    )
    return order, stock, wallet, holding, reservation


class AccountingTests(unittest.TestCase):
    def test_fee_engine_calculates_simulated_buy_and_sell_fees(self):
        fees = FeeEngine(FeeConfig(
            brokerage_bps=Decimal("10"), platform_bps=Decimal("20"), tax_bps=Decimal("5")
        ))
        calculated = fees.calculate(Decimal("3000.00"))
        self.assertEqual(calculated.brokerage, Decimal("3.00"))
        self.assertEqual(calculated.platform, Decimal("6.00"))
        self.assertEqual(calculated.taxes, Decimal("1.50"))
        self.assertEqual(calculated.total, Decimal("10.50"))

    def test_zero_fee_configuration(self):
        fees = FeeEngine(FeeConfig())
        self.assertEqual(fees.calculate(Decimal("1234.56")).total, Decimal("0.00"))

    def test_buy_settlement_records_fees_net_effect_and_cash_ledger(self):
        fees = FeeEngine(FeeConfig(brokerage_bps=Decimal("35")))
        ctx = buy_context(quantity=100, unit_price=Decimal("30.00"), fees=Decimal("10.50"))
        db = RecordingSession()
        execution = FillProcessor(fees).process_fill(
            db, order=ctx[0], stock=ctx[1], wallet=ctx[2], holding=ctx[3],
            reservation=ctx[4], fill=ExecutionFill("buy-fee", 100, Decimal("30.00")),
        )
        self.assertEqual(execution.gross_notional, Decimal("3000.00"))
        self.assertEqual(execution.fees, Decimal("10.50"))
        self.assertEqual(execution.net_cash_effect, Decimal("-3010.50"))
        self.assertEqual(execution.cost_basis, Decimal("3010.50"))
        self.assertEqual(ctx[2].balance, Decimal("6989.50"))
        entries = [item for item in db.added if isinstance(item, models.WalletTransaction)]
        self.assertEqual(
            [entry.transaction_type for entry in entries],
            ["BUY_EXECUTION", "TRADING_FEE", "ORDER_RESERVATION_RELEASE"],
        )
        self.assertEqual(sum((entry.amount for entry in entries), Decimal("0")), Decimal("-3010.50"))
        self.assertEqual(entries[1].balance_after, ctx[2].balance)
        self.assertEqual(entries[-1].amount, Decimal("0.00"))

    def test_sell_fee_is_deducted_from_proceeds_and_realized_pnl(self):
        fees = FeeEngine(FeeConfig(brokerage_bps=Decimal("35")))
        ctx = sell_context(quantity=100, unit_price=Decimal("40.00"), cost_basis=Decimal("3010.50"))
        db = RecordingSession()
        execution = FillProcessor(fees).process_fill(
            db, order=ctx[0], stock=ctx[1], wallet=ctx[2], holding=ctx[3],
            reservation=ctx[4], fill=ExecutionFill("sell-fee", 100, Decimal("40.00")),
        )
        self.assertEqual(execution.gross_notional, Decimal("4000.00"))
        self.assertEqual(execution.fees, Decimal("14.00"))
        self.assertEqual(execution.net_cash_effect, Decimal("3986.00"))
        self.assertEqual(execution.cost_basis, Decimal("3010.50"))
        self.assertEqual(execution.realized_pnl, Decimal("975.50"))
        self.assertEqual(ctx[2].balance, Decimal("13986.00"))

    def test_partial_sell_reduces_only_sold_average_cost_basis(self):
        ctx = sell_context(
            quantity=3, unit_price=Decimal("15.00"), holding_quantity=10,
            cost_basis=Decimal("103.00"),
        )
        db = RecordingSession()
        execution = FillProcessor().process_fill(
            db, order=ctx[0], stock=ctx[1], wallet=ctx[2], holding=ctx[3],
            reservation=ctx[4], fill=ExecutionFill("sell-partial", 3, Decimal("15.00")),
        )
        self.assertEqual(execution.cost_basis, Decimal("30.90"))
        self.assertEqual(execution.realized_pnl, Decimal("14.10"))
        self.assertEqual(ctx[3].quantity, 7)
        self.assertEqual(ctx[3].cost_basis, Decimal("72.10"))
        self.assertEqual(ctx[3].average_buy_price, Decimal("10.30"))

    def test_multiple_buys_and_sells_use_weighted_average_cost(self):
        db = RecordingSession()
        processor = FillProcessor()
        first = buy_context(quantity=3, unit_price=Decimal("10.00"))
        processor.process_fill(
            db, order=first[0], stock=first[1], wallet=first[2], holding=None,
            reservation=first[4], fill=ExecutionFill("buy-a", 3, Decimal("10.00")),
        )
        holding = db.holding
        second = buy_context(quantity=2, unit_price=Decimal("20.00"))
        # Reuse account balance/position while recording a separate order fill.
        second[2].balance = first[2].balance
        second[2].reserved_cash = Decimal("40.00")
        processor.process_fill(
            db, order=second[0], stock=second[1], wallet=second[2], holding=holding,
            reservation=second[4], fill=ExecutionFill("buy-b", 2, Decimal("20.00")),
        )
        self.assertEqual(holding.quantity, 5)
        self.assertEqual(holding.cost_basis, Decimal("70.00"))
        self.assertEqual(holding.average_buy_price, Decimal("14.00"))

        sale = sell_context(
            quantity=2, unit_price=Decimal("30.00"), holding_quantity=5,
            cost_basis=holding.cost_basis,
        )
        sale[3].average_buy_price = holding.average_buy_price
        execution = processor.process_fill(
            db, order=sale[0], stock=sale[1], wallet=sale[2], holding=sale[3],
            reservation=sale[4], fill=ExecutionFill("sell-a", 2, Decimal("30.00")),
        )
        self.assertEqual(execution.realized_pnl, Decimal("32.00"))
        self.assertEqual(sale[3].quantity, 3)
        self.assertEqual(sale[3].cost_basis, Decimal("42.00"))

        sale2 = sell_context(
            quantity=1, unit_price=Decimal("5.00"), holding_quantity=3,
            cost_basis=sale[3].cost_basis,
        )
        sale2[3].average_buy_price = sale[3].average_buy_price
        execution2 = processor.process_fill(
            db, order=sale2[0], stock=sale2[1], wallet=sale2[2], holding=sale2[3],
            reservation=sale2[4], fill=ExecutionFill("sell-b", 1, Decimal("5.00")),
        )
        self.assertEqual(execution2.realized_pnl, Decimal("-9.00"))
        self.assertEqual(sale2[3].quantity, 2)
        self.assertEqual(sale2[3].cost_basis, Decimal("28.00"))
        by_ref = {
            item.execution_ref: item
            for item in db.added if isinstance(item, models.Execution)
        }
        replay = [
            (by_ref["buy-a"], first[0]),
            (by_ref["buy-b"], second[0]),
            (by_ref["sell-a"], sale[0]),
            (by_ref["sell-b"], sale2[0]),
        ]
        self.assertEqual(
            PortfolioValuationService.calculate_realized_pnl(replay), Decimal("23.00")
        )

    def test_unrealized_pnl_uses_remaining_cost_basis(self):
        holding = SimpleNamespace(
            quantity=7, reserved_quantity=2, average_buy_price=Decimal("10.30"),
            cost_basis=Decimal("72.10"), total_quantity=7, available_quantity=5,
        )
        stock = SimpleNamespace(symbol="TCS", company_name="TCS", current_price=Decimal("12.00"))
        valuation = PortfolioValuationService.value_holding(holding, stock)
        self.assertEqual(valuation["market_value"], Decimal("84.00"))
        self.assertEqual(valuation["invested_value"], Decimal("72.10"))
        self.assertEqual(valuation["unrealized_pnl"], Decimal("11.90"))

    def test_fee_inclusive_buy_reservation_and_reservation_ledger(self):
        fee_config = FeeEngine(FeeConfig(platform_bps=Decimal("100")))
        order = SimpleNamespace(
            id=42, user_id=3, stock_id=7, side="BUY", order_type="LIMIT",
            quantity=10, filled_quantity=0, limit_price=Decimal("100.00"),
            stop_price=None, remaining_quantity=10,
        )
        stock = SimpleNamespace(id=7, is_active=True, current_price=Decimal("100.00"))
        wallet = SimpleNamespace(
            id=8, user_id=3, balance=Decimal("2000.00"), reserved_cash=Decimal("0.00")
        )
        db = RecordingSession()
        reservation = RiskEngine.reserve_order(
            db, order=order, stock=stock, wallet=wallet, holding=None, fees=fee_config,
        )
        self.assertEqual(reservation.reserved_cash, Decimal("1010.00"))
        self.assertEqual(wallet.reserved_cash, Decimal("1010.00"))
        ledger_entry = next(
            entry for entry in db.added
            if isinstance(entry, models.WalletTransaction)
        )
        self.assertEqual(ledger_entry.transaction_type, "ORDER_RESERVATION")
        self.assertEqual(ledger_entry.amount, Decimal("0.00"))

    def test_partial_fee_fill_keeps_only_remaining_gross_and_fee_reserved(self):
        fees = FeeEngine(FeeConfig(brokerage_bps=Decimal("35")))
        ctx = buy_context(quantity=100, unit_price=Decimal("30.00"), fees=Decimal("10.50"))
        db = RecordingSession()
        FillProcessor(fees).process_fill(
            db, order=ctx[0], stock=ctx[1], wallet=ctx[2], holding=None,
            reservation=ctx[4], fill=ExecutionFill("buy-part-fee", 30, Decimal("30.00")),
        )
        self.assertEqual(ctx[2].balance, Decimal("9096.85"))
        self.assertEqual(ctx[2].reserved_cash, Decimal("2107.35"))
        self.assertEqual(ctx[4].reserved_cash, Decimal("2107.35"))

    def test_ledger_rows_reject_orm_updates_and_deletes(self):
        entry = models.WalletTransaction(
            wallet_id=8, transaction_type="BUY_EXECUTION", amount=Decimal("-1.00"),
            balance_after=Decimal("9.00"), reference_id=4,
        )
        with self.assertRaisesRegex(ValueError, "immutable"):
            models._reject_wallet_ledger_mutation(None, None, entry)
        with self.assertRaisesRegex(ValueError, "immutable"):
            models._reject_wallet_ledger_mutation(None, None, entry)

    def test_failed_fill_requests_transaction_rollback(self):
        fees = FeeEngine(FeeConfig(brokerage_bps=Decimal("100")))
        ctx = buy_context(quantity=10, unit_price=Decimal("10.00"), fees=Decimal("10.00"))
        ctx[4].reserved_cash = Decimal("100.00")  # fee is not covered by reservation
        ctx[2].reserved_cash = Decimal("100.00")
        db = RecordingSession()
        try:
            FillProcessor(fees).process_fill(
                db, order=ctx[0], stock=ctx[1], wallet=ctx[2], holding=None,
                reservation=ctx[4], fill=ExecutionFill("underreserved", 10, Decimal("10.00")),
            )
        except ValueError:
            db.rollback()
        else:
            self.fail("under-reserved fill should fail")
        self.assertEqual(db.rollback_count, 1)


if __name__ == "__main__":
    unittest.main()
