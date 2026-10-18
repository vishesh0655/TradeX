"""Pre-trade risk checks and paper-asset reservation operations."""

from decimal import Decimal
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import models
from app.domain.orders import OrderType, validate_order_terms
from app.services.accounting_service import AccountingService
from app.services.fee_engine import FeeEngine, fee_engine
from app.services.market_data import MarketQuote, market_price_provider


class RiskRejected(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        self.status_code = status_code
        super().__init__(message)


class RiskEngine:
    """Validates orders against locked account state and maintains reservations.

    Callers lock the wallet first (the per-user serialization row), then the
    holding for SELL orders. The same lock order is used by fills/cancellations.
    """

    @staticmethod
    def validate_terms(**terms):
        """Normalize and validate side, type, quantity, and required prices."""
        return validate_order_terms(**terms)

    @staticmethod
    def find_idempotent_order(
        db: Session,
        *,
        user_id: int,
        client_order_id: str | None,
        symbol: str,
        side: str,
        order_type: str,
        quantity: int,
        limit_price: Decimal | None,
        stop_price: Decimal | None,
    ) -> models.Order | None:
        if not client_order_id:
            return None
        existing = (
            db.query(models.Order)
            .filter(
                models.Order.user_id == user_id,
                models.Order.client_order_id == client_order_id,
            )
            .first()
        )
        if existing is None:
            return None
        same_request = (
            existing.stock.symbol == symbol
            and existing.side == side
            and existing.order_type == order_type
            and existing.quantity == quantity
            and existing.limit_price == limit_price
            and existing.stop_price == stop_price
        )
        if not same_request:
            raise RiskRejected(
                "client_order_id has already been used for a different order", 409
            )
        return existing

    @staticmethod
    def validate_account(user: models.User | None, wallet: models.Wallet | None) -> None:
        if user is None or not user.is_active:
            raise RiskRejected("Trading is unavailable for this account")
        if wallet is None:
            raise RiskRejected("Wallet not found")

    @staticmethod
    def reserve_order(
        db: Session,
        *,
        order: models.Order,
        stock: models.Stock,
        wallet: models.Wallet,
        holding: models.Holding | None,
        remaining_only: bool = False,
        fees: FeeEngine | None = None,
        quote: MarketQuote | None = None,
    ) -> models.OrderReservation:
        if not stock.is_active:
            raise RiskRejected("Instrument is not tradable")

        reserve_quantity = order.remaining_quantity if remaining_only else order.quantity
        if reserve_quantity <= 0:
            raise RiskRejected("Order has no quantity remaining to reserve")

        if order.side == "BUY":
            if order.order_type == OrderType.MARKET.value:
                market_quote = quote or market_price_provider.get_quote(stock)
                if market_quote.symbol != stock.symbol:
                    raise RiskRejected("Market quote does not match the order instrument")
                reserve_price = market_quote.price
            elif order.order_type in (OrderType.LIMIT.value, OrderType.STOP_LIMIT.value):
                reserve_price = Decimal(order.limit_price)
            else:  # STOP has no cap in this phase; reserve its trigger as a cap.
                reserve_price = Decimal(order.stop_price)
            fee_calculator = fees or fee_engine
            gross_reserve = reserve_price * reserve_quantity
            amount = gross_reserve + fee_calculator.calculate(gross_reserve).total
            available = Decimal(wallet.balance) - Decimal(wallet.reserved_cash)
            if available < amount:
                raise RiskRejected(
                    f"Insufficient available cash. Available {available}, required {amount}"
                )
            wallet.reserved_cash = Decimal(wallet.reserved_cash) + amount
            reservation = models.OrderReservation(
                order_id=order.id, user_id=order.user_id, stock_id=stock.id,
                side="BUY", reserved_cash=amount, reserved_quantity=0,
                unit_price=reserve_price, state="ACTIVE",
            )
        else:
            if holding is None:
                raise RiskRejected("You do not own this stock")
            available = holding.quantity - holding.reserved_quantity
            if available < reserve_quantity:
                raise RiskRejected(
                    f"Insufficient available shares. Available {available}, "
                    f"required {reserve_quantity}"
                )
            holding.reserved_quantity += reserve_quantity
            reservation = models.OrderReservation(
                order_id=order.id, user_id=order.user_id, stock_id=stock.id,
                side="SELL", reserved_cash=Decimal("0.00"),
                reserved_quantity=reserve_quantity, unit_price=None, state="ACTIVE",
            )
        db.add(reservation)
        db.add(models.OrderEvent(
            order_id=order.id,
            event_type="RESERVATION_CREATED",
            metadata_json={
                "source": "risk_engine",
                "actor": "system",
                "reserved_cash": str(reservation.reserved_cash),
                "reserved_quantity": reservation.reserved_quantity,
            },
        ))
        AccountingService.record_reservation(
            db,
            wallet=wallet,
            order_id=order.id,
            event_type="ORDER_RESERVATION",
            reserved_cash=reservation.reserved_cash,
            reserved_quantity=reservation.reserved_quantity,
        )
        return reservation

    @staticmethod
    def apply_fill(
        *,
        order: models.Order,
        reservation: models.OrderReservation,
        wallet: models.Wallet,
        holding: models.Holding | None,
        quantity: int,
        execution_price: Decimal,
        fees: Decimal = Decimal("0.00"),
        fee_calculator: FeeEngine | None = None,
    ) -> None:
        if reservation.state != "ACTIVE" or quantity <= 0 or quantity > order.remaining_quantity:
            raise RiskRejected("Fill exceeds active order reservation")
        now = datetime.now(timezone.utc)
        reservation.updated_at = now
        wallet.updated_at = now
        if order.side == "BUY":
            gross = execution_price * quantity
            cash_cost = gross + Decimal(fees)
            if cash_cost > reservation.reserved_cash:
                raise RiskRejected("Execution exceeds reserved buying power")
            wallet.balance = Decimal(wallet.balance) - cash_cost
            remaining = order.remaining_quantity - quantity
            gross_required = Decimal(reservation.unit_price) * remaining
            calculator = fee_calculator or fee_engine
            required_after = gross_required + calculator.calculate(gross_required).total
            release = Decimal(reservation.reserved_cash) - cash_cost - required_after
            if release < 0 or required_after < 0:
                raise RiskRejected("Execution exceeds reserved buying power")
            reservation.reserved_cash = required_after
            wallet.reserved_cash = Decimal(wallet.reserved_cash) - cash_cost - release
            if remaining == 0:
                reservation.state = "SETTLED"
        else:
            if holding is None or reservation.reserved_quantity < quantity:
                raise RiskRejected("Fill exceeds reserved shares")
            if holding.quantity < quantity or holding.reserved_quantity < quantity:
                raise RiskRejected("Reserved shares are no longer available")
            holding.quantity -= quantity
            holding.reserved_quantity -= quantity
            holding.updated_at = now
            reservation.reserved_quantity -= quantity
            net_proceeds = execution_price * quantity - Decimal(fees)
            wallet.balance = Decimal(wallet.balance) + net_proceeds
            if remaining := (order.remaining_quantity - quantity):
                # remaining reservation is exactly the still-open order quantity
                if reservation.reserved_quantity != remaining:
                    raise RiskRejected("Share reservation does not match remaining order")
            else:
                reservation.state = "SETTLED"

    @staticmethod
    def reprice_buy_reservation(
        *,
        reservation: models.OrderReservation,
        wallet: models.Wallet,
        remaining_quantity: int,
        unit_price: Decimal,
        fees: FeeEngine | None = None,
        db: Session | None = None,
    ) -> bool:
        """Resize a triggered STOP BUY reservation to its actual paper price."""
        if reservation.state != "ACTIVE" or reservation.side != "BUY":
            raise RiskRejected("An active BUY reservation is required")
        gross = unit_price * remaining_quantity
        old_amount = Decimal(reservation.reserved_cash)
        new_amount = gross + (fees or fee_engine).calculate(gross).total
        difference = new_amount - Decimal(reservation.reserved_cash)
        if difference > Decimal(wallet.balance) - Decimal(wallet.reserved_cash):
            return False
        wallet.reserved_cash = Decimal(wallet.reserved_cash) + difference
        reservation.reserved_cash = new_amount
        reservation.unit_price = unit_price
        now = datetime.now(timezone.utc)
        wallet.updated_at = now
        reservation.updated_at = now
        if db is not None and new_amount != old_amount:
            AccountingService.record_reservation(
                db,
                wallet=wallet,
                order_id=reservation.order_id,
                event_type="ORDER_RESERVATION",
                reserved_cash=new_amount - old_amount,
                reserved_quantity=0,
            )
        return True

    @staticmethod
    def release(
        *,
        reservation: models.OrderReservation | None,
        wallet: models.Wallet,
        holding: models.Holding | None,
        db: Session | None = None,
    ) -> None:
        if reservation is None or reservation.state != "ACTIVE":
            return
        released_cash = reservation.reserved_cash
        released_quantity = reservation.reserved_quantity
        now = datetime.now(timezone.utc)
        reservation.updated_at = now
        wallet.updated_at = now
        if reservation.side == "BUY":
            wallet.reserved_cash = Decimal(wallet.reserved_cash) - reservation.reserved_cash
            reservation.reserved_cash = Decimal("0.00")
        else:
            amount = reservation.reserved_quantity
            if holding is not None:
                holding.reserved_quantity -= amount
                holding.updated_at = now
            reservation.reserved_quantity = 0
        reservation.state = "RELEASED"
        if db is not None:
            db.add(models.OrderEvent(
                order_id=reservation.order_id,
                event_type="RESERVATION_RELEASED",
                metadata_json={
                    "source": "risk_engine",
                    "actor": "system",
                    "reserved_cash": str(released_cash),
                    "reserved_quantity": released_quantity,
                },
            ))
            AccountingService.record_reservation(
                db,
                wallet=wallet,
                order_id=reservation.order_id,
                event_type="ORDER_RESERVATION_RELEASE",
                reserved_cash=Decimal(released_cash),
                reserved_quantity=released_quantity,
            )
