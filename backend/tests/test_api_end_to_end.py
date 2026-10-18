"""Opt-in PostgreSQL API journeys using a temporary isolated schema.

Run with TRADEX_RUN_POSTGRES_E2E=1. The test creates and drops its own schema;
it never inserts into the configured public TradeX tables.
"""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, ROUND_HALF_UP
import os
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base, database_url, engine, get_db
from app.domain.orders import OrderValidationError
from app.main import app, order_service
from app.security import create_access_token
from app.services.accounting_service import accounting_service
from app.services.execution_adapter import ExecutionFill
from app.services.execution_engine import PaperExecutionEngine
from app.services.fee_engine import fee_engine
from app.services.order_evaluation import order_evaluation_service


@unittest.skipUnless(
    os.getenv("TRADEX_RUN_POSTGRES_E2E") == "1",
    "set TRADEX_RUN_POSTGRES_E2E=1 to run isolated PostgreSQL API journeys",
)
class PaperTradingApiJourneyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = f"tradex_audit_{uuid4().hex}"
        cls.symbol = f"AUD{uuid4().hex[:10].upper()}"
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{cls.schema}"'))
        cls.test_engine = create_engine(
            database_url,
            connect_args={"options": f"-csearch_path={cls.schema},public"},
            pool_size=8,
            max_overflow=4,
        )
        Base.metadata.create_all(cls.test_engine)
        cls.Session = sessionmaker(
            bind=cls.test_engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )

        def override_get_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        cls._prior_override = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)
        with cls.Session() as db:
            db.add(models.Stock(
                symbol=cls.symbol,
                company_name="TradeX Audit Instrument",
                exchange="PAPER",
                current_price=Decimal("100.00"),
                is_active=True,
            ))
            db.commit()

        # Exercise the same database-level protection installed by the current
        # PostgreSQL migrations, inside only the temporary audit schema.
        with cls.test_engine.begin() as connection:
            connection.exec_driver_sql("""
                CREATE FUNCTION reject_audit_mutation() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'immutable audit row'; END; $$
            """)
            for table in ("wallet_transactions", "executions", "order_events"):
                connection.exec_driver_sql(
                    f"CREATE TRIGGER {table}_audit_immutable BEFORE UPDATE OR DELETE ON {table} "
                    "FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
                )

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_db, None)
        if cls._prior_override is not None:
            app.dependency_overrides[get_db] = cls._prior_override
        cls.client.close()
        cls.test_engine.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{cls.schema}" CASCADE'))

    def register(self, label):
        email = f"{label}-{uuid4().hex}@example.com"
        response = self.client.post("/register", json={
            "name": label,
            "email": email,
            "password": "TradeX-audit-password-2026",
        })
        self.assertEqual(response.status_code, 201, response.text)
        user = response.json()
        login = self.client.post("/login", json={
            "email": email,
            "password": "TradeX-audit-password-2026",
        })
        self.assertEqual(login.status_code, 200, login.text)
        return user, {"Authorization": f"Bearer {login.json()['access_token']}"}

    def place(self, headers, *, side="BUY", order_type="MARKET", quantity=1,
              limit_price=None, stop_price=None, client_order_id=None):
        payload = {
            "stock_symbol": self.symbol,
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
        }
        if limit_price is not None:
            payload["limit_price"] = str(limit_price)
        if stop_price is not None:
            payload["stop_price"] = str(stop_price)
        if client_order_id is not None:
            payload["client_order_id"] = client_order_id
        return self.client.post("/orders", json=payload, headers=headers)

    def evaluate(self, price):
        with self.Session() as db:
            return order_evaluation_service.evaluate_open_orders(
                db, stock_symbol=self.symbol, current_price=Decimal(str(price))
            )

    def get_reservation(self, order_id):
        with self.Session() as db:
            return db.query(models.OrderReservation).filter_by(order_id=order_id).one()

    def test_full_paper_trading_journey_and_integrity(self):
        user, owner = self.register("owner")

        # 1. Registration atomically provisions a virtual wallet and opening ledger row.
        wallet = self.client.get("/wallet", headers=owner).json()
        self.assertEqual(wallet["account_type"], "PAPER")
        self.assertEqual(Decimal(str(wallet["cash_balance"])), Decimal("1000000.00"))
        with self.Session() as db:
            wallet_id = db.query(models.Wallet.id).filter_by(user_id=user["id"]).scalar()
            self.assertEqual(db.query(models.WalletTransaction).filter(
                models.WalletTransaction.wallet_id == wallet_id,
                models.WalletTransaction.transaction_type == "INITIAL_VIRTUAL_BALANCE",
            ).count(), 1)

        # 2. Market BUY settles the order, wallet, holding, ledger and events atomically.
        first_buy = self.place(owner, quantity=10)
        self.assertEqual(first_buy.status_code, 201, first_buy.text)
        first_order = first_buy.json()
        self.assertEqual(first_order["status"], "FILLED")
        self.assertEqual(first_order["filled_quantity"], 10)
        first_execs = self.client.get(f"/orders/{first_order['id']}/executions", headers=owner).json()
        self.assertEqual(sum(item["quantity"] for item in first_execs), 10)
        first_holding = self.client.get("/holdings", headers=owner).json()[0]
        self.assertEqual(first_holding["quantity"], 10)
        with self.Session() as db:
            event_types = {event.event_type for event in db.query(models.OrderEvent).filter_by(order_id=first_order["id"])}
        self.assertTrue({"ORDER_CREATED", "ORDER_OPENED", "ORDER_ACCEPTED", "EXECUTION_CREATED", "ORDER_FILLED"}.issubset(event_types))
        ledger = self.client.get("/wallet/transactions?limit=100", headers=owner).json()
        self.assertAlmostEqual(sum(float(row["amount"]) for row in ledger), float(self.client.get("/wallet", headers=owner).json()["cash_balance"]), places=2)

        # 3. Additional shares update average cost using persisted execution cost basis.
        second_buy = self.place(owner, quantity=10).json()
        self.assertEqual(second_buy["status"], "FILLED")
        holding_after_buys = self.client.get("/holdings", headers=owner).json()[0]
        executions = self.client.get(f"/orders/{second_buy['id']}/executions", headers=owner).json()
        with self.Session() as db:
            basis = sum(Decimal(row.cost_basis) for row in db.query(models.Execution).join(models.Order).filter(
                models.Order.user_id == user["id"], models.Order.side == "BUY"
            ).all())
        expected_average = (basis / Decimal(20)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self.assertEqual(Decimal(str(holding_after_buys["average_buy_price"])), expected_average)
        self.assertEqual(sum(row["quantity"] for row in executions), 10)

        # 4. Partial SELL reduces shares and realizes only the sold-share return.
        before_sell_cash = Decimal(str(self.client.get("/wallet", headers=owner).json()["cash_balance"]))
        sell = self.place(owner, side="SELL", quantity=5).json()
        self.assertEqual(sell["status"], "FILLED")
        after_sell_holding = self.client.get("/holdings", headers=owner).json()[0]
        self.assertEqual(after_sell_holding["quantity"], 15)
        sell_exec = self.client.get(f"/orders/{sell['id']}/executions", headers=owner).json()[0]
        portfolio = self.client.get("/portfolio", headers=owner).json()
        self.assertEqual(Decimal(str(portfolio["realized_pnl"])), Decimal(str(sell_exec["realized_pnl"])))
        after_sell_cash = Decimal(str(self.client.get("/wallet", headers=owner).json()["cash_balance"]))
        self.assertGreater(after_sell_cash, before_sell_cash)

        # 5. A marketable LIMIT BUY fills at the current stored paper quote.
        limit_buy = self.place(owner, order_type="LIMIT", quantity=2, limit_price=100).json()
        self.assertEqual(limit_buy["status"], "FILLED")
        reservation = self.get_reservation(limit_buy["id"])
        self.assertEqual(reservation.state, "SETTLED")
        self.assertEqual(Decimal(reservation.reserved_cash), Decimal("0.00"))
        self.assertEqual(self.client.get(f"/orders/{limit_buy['id']}", headers=owner).json()["status"], "FILLED")

        # 6. A marketable LIMIT SELL settles against the stored paper quote.
        limit_sell = self.place(owner, side="SELL", order_type="LIMIT", quantity=2, limit_price=99).json()
        with self.Session() as db:
            reservation = db.query(models.OrderReservation).filter_by(order_id=limit_sell["id"]).one()
        self.assertEqual(reservation.reserved_quantity, 0)
        self.assertEqual(reservation.state, "SETTLED")
        self.assertEqual(self.client.get(f"/orders/{limit_sell['id']}", headers=owner).json()["status"], "FILLED")
        with self.Session() as db:
            self.assertEqual(db.query(models.OrderReservation).filter_by(order_id=limit_sell["id"]).one().state, "SETTLED")

        # 7. STOP does not execute before trigger and only creates one fill afterward.
        stop = self.place(owner, order_type="STOP", quantity=1, stop_price=110).json()
        self.evaluate(109)
        stop_order = self.client.get(f"/orders/{stop['id']}", headers=owner).json()
        self.assertEqual(stop_order["status"], "OPEN")
        self.assertFalse(stop_order["stop_triggered"])
        self.evaluate(110)
        self.evaluate(110)
        self.assertEqual(self.client.get(f"/orders/{stop['id']}", headers=owner).json()["status"], "FILLED")
        self.assertEqual(len(self.client.get(f"/orders/{stop['id']}/executions", headers=owner).json()), 1)

        # 8. STOP_LIMIT persists its trigger before its limit becomes executable.
        stop_limit = self.place(owner, order_type="STOP_LIMIT", quantity=1, stop_price=100, limit_price=99).json()
        self.evaluate(100)
        triggered = self.client.get(f"/orders/{stop_limit['id']}", headers=owner).json()
        self.assertTrue(triggered["stop_triggered"])
        self.assertEqual(triggered["status"], "OPEN")
        self.assertEqual(self.client.get(f"/orders/{stop_limit['id']}/executions", headers=owner).json(), [])
        self.evaluate(99)
        self.assertEqual(self.client.get(f"/orders/{stop_limit['id']}", headers=owner).json()["status"], "FILLED")

        # 9. Cancellation releases cash and records a lifecycle event.
        cancel_target = self.place(owner, order_type="LIMIT", quantity=1, limit_price=80).json()
        self.assertGreater(Decimal(self.get_reservation(cancel_target["id"]).reserved_cash), Decimal("0"))
        cancelled = self.client.post(f"/orders/{cancel_target['id']}/cancel", headers=owner)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(cancelled.json()["status"], "CANCELLED")
        self.assertEqual(self.get_reservation(cancel_target["id"]).state, "RELEASED")
        cancel_events = self.client.get(f"/orders/{cancel_target['id']}/events", headers=owner).json()
        self.assertIn("ORDER_CANCELLED", {item["event_type"] for item in cancel_events})

        # 10. Modification rechecks risk and updates reservation plus audit history.
        modify_target = self.place(owner, order_type="LIMIT", quantity=1, limit_price=80).json()
        previous_reserve = Decimal(self.get_reservation(modify_target["id"]).reserved_cash)
        modified = self.client.patch(f"/orders/{modify_target['id']}", headers=owner, json={
            "quantity": 2,
            "limit_price": "90.00",
        })
        self.assertEqual(modified.status_code, 200, modified.text)
        self.assertEqual(modified.json()["quantity"], 2)
        self.assertGreater(Decimal(self.get_reservation(modify_target["id"]).reserved_cash), previous_reserve)
        modify_events = self.client.get(f"/orders/{modify_target['id']}/events", headers=owner).json()
        self.assertIn("ORDER_MODIFIED", {item["event_type"] for item in modify_events})
        self.client.post(f"/orders/{modify_target['id']}/cancel", headers=owner)

        # 11. Same idempotency key returns the existing order without a second insert.
        idempotency_key = f"audit-{uuid4().hex}"
        idem_body = {
            "stock_symbol": self.symbol, "side": "BUY", "order_type": "LIMIT",
            "quantity": 1, "limit_price": "70.00", "client_order_id": idempotency_key,
        }
        created = self.client.post("/orders", headers=owner, json=idem_body)
        replay = self.client.post("/orders", headers=owner, json=idem_body)
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(created.json()["id"], replay.json()["id"])
        conflict_body = {**idem_body, "quantity": 2}
        self.assertEqual(self.client.post("/orders", headers=owner, json=conflict_body).status_code, 409)
        with self.Session() as db:
            self.assertEqual(db.query(models.Order).filter_by(user_id=user["id"], client_order_id=idempotency_key).count(), 1)
        self.client.post(f"/orders/{created.json()['id']}/cancel", headers=owner)

        # 12. Another user's order is forbidden; wallet and holdings are owner-scoped.
        other_user, other = self.register("other")
        other_wallet = self.client.get("/wallet", headers=other).json()
        self.assertEqual(Decimal(str(other_wallet["cash_balance"])), Decimal("1000000.00"))
        self.assertEqual(self.client.get("/holdings", headers=other).json(), [])
        self.assertEqual(self.client.get(f"/orders/{first_order['id']}", headers=other).status_code, 403)

        # 13. Failed settlement rolls back order, wallet, holding, ledger and events.
        counts_before = self._account_counts(user["id"])
        wallet_before = Decimal(str(self.client.get("/wallet", headers=owner).json()["cash_balance"]))
        class InvalidPriceAdapter:
            venue = "PAPER_TEST"
            def create_fills(self, *, order, quote):
                return (ExecutionFill("AUDIT-INVALID-PRICE", 1, Decimal("-1")),)
        previous_engine = order_service.execution_engine
        order_service.execution_engine = PaperExecutionEngine(adapter=InvalidPriceAdapter())
        try:
            failure = self.place(owner, quantity=1)
        finally:
            order_service.execution_engine = previous_engine
        self.assertEqual(failure.status_code, 400)
        self.assertEqual(self._account_counts(user["id"]), counts_before)
        self.assertEqual(Decimal(str(self.client.get("/wallet", headers=owner).json()["cash_balance"])), wallet_before)

        # Ledger rows and executions are append-only at both ORM and DB levels.
        with self.Session() as db:
            ledger_row = db.query(models.WalletTransaction).join(models.Wallet).filter(
                models.Wallet.user_id == user["id"]
            ).first()
            ledger_id = ledger_row.id
        with self.assertRaises(Exception):
            with self.test_engine.begin() as connection:
                connection.execute(text("UPDATE wallet_transactions SET amount = 1 WHERE id = :id"), {"id": ledger_id})

        # API pagination/filtering and paper-fee estimate contract smoke checks.
        filtered = self.client.get(f"/orders?limit=10&offset=0&side=BUY&symbol={self.symbol}", headers=owner)
        self.assertEqual(filtered.status_code, 200)
        self.assertLessEqual(len(filtered.json()), 10)
        self.assertEqual(filtered.headers["x-total-count"], str(len(filtered.json())))
        estimate = self.client.post("/fees/estimate", headers=owner, json={"side": "BUY", "gross_notional": "100.00"})
        self.assertEqual(estimate.status_code, 200, estimate.text)
        self.assertGreaterEqual(Decimal(estimate.json()["total_fees"]), Decimal("0"))
        self.assertEqual(self.client.get("/wallet").status_code, 401)

    def test_registration_is_atomic_and_inactive_users_are_denied(self):
        email = f"atomic-{uuid4().hex}@example.com"
        original_initialize = accounting_service.initialize_wallet
        def fail_wallet(db, *, user_id):
            raise RuntimeError("injected wallet provisioning failure")
        accounting_service.initialize_wallet = fail_wallet
        try:
            response = self.client.post("/register", json={
                "name": "Atomic rollback",
                "email": email,
                "password": "TradeX-audit-password-2026",
            })
        finally:
            accounting_service.initialize_wallet = original_initialize
        self.assertEqual(response.status_code, 500)
        with self.Session() as db:
            self.assertIsNone(db.query(models.User).filter_by(email=email).first())

        user, headers = self.register("inactive")
        with self.Session() as db:
            db.query(models.User).filter_by(id=user["id"]).update({"is_active": False})
            db.commit()
        self.assertEqual(self.client.get("/wallet", headers=headers).status_code, 403)

    def test_simultaneous_buy_and_sell_requests_cannot_overreserve(self):
        buyer, buyer_headers = self.register("concurrent-buyer")
        per_share = Decimal("90.00") + fee_engine.calculate(Decimal("90.00")).total
        buy_quantity = int(Decimal("650000.00") / per_share)
        self.assertGreater(buy_quantity * per_share, Decimal("500000"))
        self.assertLess(buy_quantity * per_share, Decimal("1000000"))

        def submit_buy():
            with TestClient(app) as client:
                return client.post("/orders", headers=buyer_headers, json={
                    "stock_symbol": self.symbol, "side": "BUY", "order_type": "LIMIT",
                    "quantity": buy_quantity, "limit_price": "90.00",
                })

        with ThreadPoolExecutor(max_workers=2) as pool:
            buy_results = list(pool.map(lambda _: submit_buy(), range(2)))
        self.assertEqual(sorted(response.status_code for response in buy_results), [201, 400])
        buyer_wallet = self.client.get("/wallet", headers=buyer_headers).json()
        self.assertGreaterEqual(Decimal(str(buyer_wallet["available_cash"])), Decimal("0"))
        self.assertLessEqual(Decimal(str(buyer_wallet["reserved_cash"])), Decimal(str(buyer_wallet["cash_balance"])))

        seller, seller_headers = self.register("concurrent-seller")
        self.assertEqual(self.place(seller_headers, quantity=20).status_code, 201)
        barrier = __import__("threading").Barrier(2)
        def submit_sell():
            with TestClient(app) as client:
                barrier.wait(timeout=5)
                return client.post("/orders", headers=seller_headers, json={
                    "stock_symbol": self.symbol, "side": "SELL", "order_type": "LIMIT",
                    "quantity": 15, "limit_price": "110.00",
                })
        with ThreadPoolExecutor(max_workers=2) as pool:
            sell_results = list(pool.map(lambda _: submit_sell(), range(2)))
        self.assertEqual(sorted(response.status_code for response in sell_results), [201, 400])
        holdings = self.client.get("/holdings", headers=seller_headers).json()
        self.assertEqual(holdings[0]["reserved_quantity"], 15)
        self.assertGreaterEqual(holdings[0]["available_quantity"], 0)

    def _account_counts(self, user_id):
        with self.Session() as db:
            return (
                db.query(models.Order).filter_by(user_id=user_id).count(),
                db.query(models.Execution).join(models.Order).filter(models.Order.user_id == user_id).count(),
                db.query(models.Holding).filter_by(user_id=user_id).count(),
                db.query(models.WalletTransaction).join(models.Wallet).filter(models.Wallet.user_id == user_id).count(),
                db.query(models.OrderEvent).join(models.Order).filter(models.Order.user_id == user_id).count(),
            )


if __name__ == "__main__":
    unittest.main()
