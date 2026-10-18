"""Transactional settlement of individual paper executions."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.services.accounting_service import AccountingService
from app.services.execution_adapter import ExecutionFill
from app.services.fee_engine import FeeEngine, fee_engine
from app.services.order_lifecycle import transition_order
from app.services.risk_engine import RiskEngine


class FillProcessingError(ValueError):
    pass


class DuplicateExecution(FillProcessingError):
    pass


class FillProcessor:
    """Apply one execution to the order, reservation, account, ledger and events.

    `process_fill` accepts already locked entities for use inside an enclosing
    order transaction. `execute_fill` acquires the locks for later/asynchronous
    paper fills and leaves commit ownership to the caller.
    """

    def __init__(self, fees: FeeEngine | None = None):
        self.fees = fees or fee_engine

    def execute_fill(
        self, db: Session, *, order_id: int, fill: ExecutionFill
    ) -> models.Execution:
        try:
            identity = db.query(models.Order.user_id).filter(
                models.Order.id == order_id
            ).scalar()
            if identity is None:
                raise FillProcessingError("Order not found")
            user_id = identity
            wallet = (
                db.query(models.Wallet)
                .filter(models.Wallet.user_id == user_id)
                .with_for_update()
                .first()
            )
            if wallet is None:
                raise FillProcessingError("Wallet not found")
            order = (
                db.query(models.Order)
                .filter(models.Order.id == order_id)
                .with_for_update()
                .first()
            )
            if order is None:
                raise FillProcessingError("Order not found")
            stock = db.query(models.Stock).filter(models.Stock.id == order.stock_id).first()
            holding = (
                db.query(models.Holding)
                .filter(
                    models.Holding.user_id == user_id,
                    models.Holding.stock_id == order.stock_id,
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
                raise FillProcessingError("Active order reservation not found")
            return self.process_fill(
                db,
                order=order,
                stock=stock,
                wallet=wallet,
                holding=holding,
                reservation=reservation,
                fill=fill,
            )
        except IntegrityError as exc:
            db.rollback()
            if db.query(models.Execution.id).filter(
                models.Execution.execution_ref == fill.execution_ref
            ).first() is not None:
                raise DuplicateExecution(
                    "Execution reference has already been processed"
                ) from exc
            raise FillProcessingError("Execution could not be recorded") from exc
        except Exception:
            db.rollback()
            raise

    def process_fill(
        self,
        db: Session,
        *,
        order: models.Order,
        stock: models.Stock,
        wallet: models.Wallet,
        holding: models.Holding | None,
        reservation: models.OrderReservation,
        fill: ExecutionFill,
    ) -> models.Execution:
        if order.status not in {"OPEN", "PARTIALLY_FILLED"}:
            raise FillProcessingError("Only open orders can be settled")
        if stock is None or order.stock_id != stock.id:
            raise FillProcessingError("Execution instrument does not match order")
        if wallet.user_id != order.user_id:
            raise FillProcessingError("Execution wallet does not match order owner")
        if (
            reservation.order_id != order.id
            or reservation.user_id != order.user_id
            or reservation.stock_id != order.stock_id
        ):
            raise FillProcessingError("Execution reservation does not match order")
        if holding is not None and (
            holding.user_id != order.user_id or holding.stock_id != order.stock_id
        ):
            raise FillProcessingError("Execution holding does not match order")
        if order.filled_quantity < 0 or order.filled_quantity > order.quantity:
            raise FillProcessingError("Order has an invalid filled quantity")
        if order.order_type in {"STOP", "STOP_LIMIT"} and not order.stop_triggered:
            raise FillProcessingError("Stop order has not been triggered")
        if (
            not isinstance(fill.quantity, int)
            or isinstance(fill.quantity, bool)
            or fill.quantity <= 0
            or fill.quantity > order.remaining_quantity
        ):
            raise FillProcessingError("Execution quantity exceeds remaining order quantity")
        try:
            price = Decimal(fill.execution_price)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise FillProcessingError("Execution price must be positive") from exc
        if not price.is_finite() or price <= 0:
            raise FillProcessingError("Execution price must be positive")
        if order.order_type in {"LIMIT", "STOP_LIMIT"}:
            limit_price = Decimal(order.limit_price)
            if order.side == "BUY" and price > limit_price:
                raise FillProcessingError("BUY execution is above its limit price")
            if order.side == "SELL" and price < limit_price:
                raise FillProcessingError("SELL execution is below its limit price")
        if not fill.execution_ref or len(fill.execution_ref) > 100:
            raise FillProcessingError("Execution reference is required")
        if db.query(models.Execution).filter(
            models.Execution.execution_ref == fill.execution_ref
        ).first() is not None:
            raise DuplicateExecution("Execution reference has already been processed")

        prior_filled = order.filled_quantity
        prior_average = order.average_fill_price
        next_filled = prior_filled + fill.quantity
        balance_before = Decimal(wallet.balance)
        gross_notional = price * fill.quantity
        fee_breakdown = self.fees.calculate(gross_notional)
        prior_reserved_cash = Decimal(reservation.reserved_cash)
        prior_reserved_quantity = reservation.reserved_quantity
        cost_basis = Decimal("0.00")
        realized_pnl = Decimal("0.00")
        if order.side == "BUY":
            if holding is None:
                average_cost = (gross_notional + fee_breakdown.total) / fill.quantity
                holding = models.Holding(
                    user_id=order.user_id,
                    stock_id=order.stock_id,
                    quantity=fill.quantity,
                    reserved_quantity=0,
                    average_buy_price=average_cost.quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    ),
                    cost_basis=gross_notional + fee_breakdown.total,
                )
                db.add(holding)
            else:
                old_cost_basis = Decimal(
                    getattr(holding, "cost_basis", None)
                    or Decimal(holding.average_buy_price) * holding.quantity
                )
                new_cost_basis = old_cost_basis + gross_notional + fee_breakdown.total
                holding.quantity += fill.quantity
                holding.cost_basis = new_cost_basis
                holding.average_buy_price = (new_cost_basis / holding.quantity).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            cost_basis = gross_notional + fee_breakdown.total
        elif order.side == "SELL":
            if holding is None or holding.quantity < fill.quantity:
                raise FillProcessingError("Insufficient shares for execution")
            current_cost_basis = Decimal(
                getattr(holding, "cost_basis", None)
                or Decimal(holding.average_buy_price) * holding.quantity
            )
            cost_basis = (
                current_cost_basis
                if fill.quantity == holding.quantity
                else (current_cost_basis * fill.quantity / holding.quantity).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            )
            realized_pnl = gross_notional - fee_breakdown.total - cost_basis
        else:
            raise FillProcessingError("Unsupported order side")

        try:
            RiskEngine.apply_fill(
                order=order,
                reservation=reservation,
                wallet=wallet,
                holding=holding,
                quantity=fill.quantity,
                execution_price=price,
                fees=fee_breakdown.total,
                fee_calculator=self.fees,
            )
        except ValueError as exc:
            raise FillProcessingError(str(exc)) from exc

        avg_price = (
            price
            if prior_filled == 0
            else (
                Decimal(prior_average) * prior_filled + price * fill.quantity
            ) / next_filled
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        order.filled_quantity = next_filled
        order.average_fill_price = avg_price

        execution = models.Execution(
            order_id=order.id,
            execution_ref=fill.execution_ref,
            quantity=fill.quantity,
            execution_price=price,
            executed_at=fill.executed_at or datetime.now(timezone.utc),
            gross_notional=gross_notional,
            fees=fee_breakdown.total,
            net_cash_effect=(
                -(gross_notional + fee_breakdown.total)
                if order.side == "BUY"
                else gross_notional - fee_breakdown.total
            ),
            cost_basis=cost_basis,
            realized_pnl=realized_pnl,
        )
        db.add(execution)
        AccountingService.record_execution_cash_flow(
            db,
            wallet=wallet,
            order_id=order.id,
            side=order.side,
            gross_notional=gross_notional,
            fees=fee_breakdown,
            balance_before=balance_before,
            balance_after=Decimal(wallet.balance),
        )
        if (prior_reserved_cash != Decimal(reservation.reserved_cash)
                or prior_reserved_quantity != reservation.reserved_quantity):
            AccountingService.record_reservation(
                db,
                wallet=wallet,
                order_id=order.id,
                event_type="ORDER_RESERVATION_RELEASE",
                reserved_cash=prior_reserved_cash - Decimal(reservation.reserved_cash),
                reserved_quantity=prior_reserved_quantity - reservation.reserved_quantity,
            )
        db.add(models.OrderEvent(
            order_id=order.id,
            event_type="EXECUTION_CREATED",
            metadata_json={
                "source": "paper_execution",
                "actor": "system",
                "execution_ref": fill.execution_ref,
                "quantity": fill.quantity,
                "execution_price": str(price),
                "filled_quantity": next_filled,
                "remaining_quantity": order.quantity - next_filled,
                "average_fill_price": str(avg_price),
                "reservation_state": reservation.state,
                "gross_notional": str(gross_notional),
                "fees": {
                    "brokerage": str(fee_breakdown.brokerage),
                    "platform": str(fee_breakdown.platform),
                    "taxes": str(fee_breakdown.taxes),
                    "total": str(fee_breakdown.total),
                },
                "net_cash_effect": str(execution.net_cash_effect),
                "cost_basis": str(cost_basis),
                "realized_pnl": str(realized_pnl),
            },
        ))

        if next_filled == order.quantity:
            transition_order(
                db, order, "FILLED", event_type="ORDER_FILLED",
                metadata={
                    "filled_quantity": next_filled,
                    "average_fill_price": str(avg_price),
                },
            )
        elif order.status == "OPEN":
            transition_order(
                db, order, "PARTIALLY_FILLED", event_type="ORDER_PARTIALLY_FILLED",
                metadata={
                    "filled_quantity": next_filled,
                    "remaining_quantity": order.quantity - next_filled,
                    "average_fill_price": str(avg_price),
                },
            )

        if order.side == "SELL" and holding is not None and holding.quantity == 0:
            if holding.reserved_quantity != 0:
                raise FillProcessingError("Cannot remove a holding with reserved shares")
            db.delete(holding)
        elif order.side == "SELL" and holding is not None:
            holding.cost_basis = current_cost_basis - cost_basis
            holding.average_buy_price = (holding.cost_basis / holding.quantity).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        db.flush()
        return execution
