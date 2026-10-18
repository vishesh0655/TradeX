"""Price-event driven evaluation for open paper orders."""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app import models
from app.services.execution_engine import PaperExecutionEngine
from app.services.order_lifecycle import transition_order
from app.services.risk_engine import RiskEngine, RiskRejected
from app.services.market_data import MarketPriceProvider, MarketQuote, market_price_provider


class OrderEvaluationError(ValueError):
    pass


@dataclass(frozen=True)
class EvaluationReport:
    orders_evaluated: int = 0
    stop_orders_triggered: int = 0
    orders_filled: int = 0
    orders_partially_filled: int = 0
    orders_rejected: int = 0


class OrderEvaluationService:
    """Evaluates orders against a supplied price; it never creates prices.

    Each call is a single database transaction. Candidate IDs are read first,
    then account rows are locked before orders, holdings, and reservations to
    match the order-entry/cancel/fill lock sequence.
    """

    def __init__(
        self,
        execution_engine: PaperExecutionEngine | None = None,
        price_provider: MarketPriceProvider | None = None,
    ):
        self.execution_engine = execution_engine or PaperExecutionEngine()
        self.price_provider = price_provider or market_price_provider

    @staticmethod
    def _stop_condition(order: models.Order, price: Decimal) -> bool:
        if order.side == "BUY":
            return price >= Decimal(order.stop_price)
        return price <= Decimal(order.stop_price)

    @staticmethod
    def _limit_condition(order: models.Order, price: Decimal) -> bool:
        if order.side == "BUY":
            return price <= Decimal(order.limit_price)
        return price >= Decimal(order.limit_price)

    def _is_eligible(self, order: models.Order, price: Decimal) -> tuple[bool, bool]:
        """Return (eligible, newly_triggered)."""
        if order.order_type == "LIMIT":
            return self._limit_condition(order, price), False
        if order.order_type == "STOP":
            if order.stop_triggered:
                return True, False
            triggered = self._stop_condition(order, price)
            return triggered, triggered
        if order.order_type == "STOP_LIMIT":
            if order.stop_triggered:
                return self._limit_condition(order, price), False
            newly_triggered = self._stop_condition(order, price)
            return (
                self._limit_condition(order, price) if newly_triggered else False,
                newly_triggered,
            )
        return False, False

    def evaluate_open_orders(
        self,
        db: Session,
        *,
        stock_symbol: str,
        current_price: Decimal | int | float | str | None = None,
        order_id: int | None = None,
        commit: bool = True,
    ) -> EvaluationReport:
        symbol = stock_symbol.strip().upper()
        if not symbol:
            raise OrderEvaluationError("Stock symbol is required")
        try:
            stock = (
                db.query(models.Stock)
                .filter(models.Stock.symbol == symbol, models.Stock.is_active.is_(True))
                .first()
            )
            if stock is None:
                raise OrderEvaluationError("Tradable stock not found")
            try:
                quote = (
                    self.price_provider.get_quote(stock)
                    if current_price is None
                    else MarketQuote(
                        symbol=stock.symbol,
                        price=Decimal(str(current_price)),
                        observed_at=datetime.now(timezone.utc),
                        source="SUPPLIED_PAPER_PRICE",
                    )
                )
                price = quote.price
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise OrderEvaluationError("Current price must be positive") from exc
            if quote.symbol != stock.symbol:
                raise OrderEvaluationError("Current price does not match the instrument")
            if not price.is_finite() or price <= 0:
                raise OrderEvaluationError("Current price must be positive")

            # Callers may have just transitioned an inserted order to OPEN in
            # a session configured with autoflush=False. Flush that state before
            # selecting eligible candidates inside the same transaction.
            db.flush()
            candidate_query = db.query(models.Order.id, models.Order.user_id).filter(
                models.Order.stock_id == stock.id,
                models.Order.status.in_(("OPEN", "PARTIALLY_FILLED")),
            )
            if order_id is not None:
                candidate_query = candidate_query.filter(models.Order.id == order_id)
            candidates = candidate_query.order_by(models.Order.user_id, models.Order.id).all()
            evaluated = triggered = filled = partial = rejected = 0
            for candidate in candidates:
                order_id, user_id = candidate[0], candidate[1]
                wallet = (
                    db.query(models.Wallet)
                    .filter(models.Wallet.user_id == user_id)
                    .with_for_update()
                    .first()
                )
                if wallet is None:
                    continue
                order = (
                    db.query(models.Order)
                    .filter(
                        models.Order.id == order_id,
                        models.Order.user_id == user_id,
                    )
                    .with_for_update()
                    .first()
                )
                if order is None or order.status not in {"OPEN", "PARTIALLY_FILLED"}:
                    continue
                evaluated += 1
                holding = (
                    db.query(models.Holding)
                    .filter(
                        models.Holding.user_id == user_id,
                        models.Holding.stock_id == stock.id,
                    )
                    .with_for_update()
                    .first()
                )
                reservation = (
                    db.query(models.OrderReservation)
                    .filter(models.OrderReservation.order_id == order.id)
                    .with_for_update()
                    .first()
                )
                if reservation is None:
                    try:
                        reservation = RiskEngine.reserve_order(
                            db,
                            order=order,
                            stock=stock,
                            wallet=wallet,
                            holding=holding,
                            remaining_only=True,
                            quote=quote,
                        )
                    except RiskRejected as exc:
                        transition_order(
                            db,
                            order,
                            "REJECTED",
                            event_type="ORDER_REJECTED",
                            metadata={"reason": str(exc), "source": "ORDER_EVALUATION"},
                        )
                        rejected += 1
                        continue

                eligible, newly_triggered = self._is_eligible(order, price)
                if newly_triggered:
                    order.stop_triggered = True
                    order.triggered_at = datetime.now(timezone.utc)
                    triggered += 1
                    db.add(models.OrderEvent(
                        order_id=order.id,
                        event_type="STOP_TRIGGERED",
                        metadata_json={
                            "source": "order_evaluation",
                            "actor": "system",
                            "stop_price": str(order.stop_price),
                            "trigger_price": str(price),
                            "triggered_at": order.triggered_at.isoformat(),
                        },
                    ))

                if not eligible:
                    continue

                if order.order_type == "STOP" and order.side == "BUY":
                    reservation_fits = RiskEngine.reprice_buy_reservation(
                        reservation=reservation,
                        wallet=wallet,
                        remaining_quantity=order.remaining_quantity,
                        unit_price=price,
                        db=db,
                    )
                    if not reservation_fits:
                        RiskEngine.release(
                            reservation=reservation,
                            wallet=wallet,
                            holding=holding,
                            db=db,
                        )
                        transition_order(
                            db,
                            order,
                            "REJECTED",
                            event_type="ORDER_REJECTED",
                            metadata={
                                "reason": "Insufficient available cash at stop trigger price",
                                "source": "ORDER_EVALUATION",
                            },
                        )
                        rejected += 1
                        continue

                self.execution_engine.execute_eligible_order(
                    db,
                    order=order,
                    stock=stock,
                    wallet=wallet,
                    holding=holding,
                    reservation=reservation,
                    quote=quote,
                )
                if order.status == "FILLED":
                    filled += 1
                elif order.status == "PARTIALLY_FILLED":
                    partial += 1

            if commit:
                db.commit()
            return EvaluationReport(evaluated, triggered, filled, partial, rejected)
        except Exception:
            db.rollback()
            raise


order_evaluation_service = OrderEvaluationService()
