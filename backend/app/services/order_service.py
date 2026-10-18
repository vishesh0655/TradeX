from decimal import Decimal
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import models
from app.domain.orders import OrderType, OrderValidationError
from app.services.execution_engine import PaperExecutionEngine
from app.services.accounting_service import AccountingService
from app.services.fee_engine import fee_engine
from app.services.order_lifecycle import InvalidOrderTransition, transition_order
from app.services.risk_engine import RiskEngine, RiskRejected
from app.services.market_data import MarketPriceProvider, market_price_provider
from app.services.order_evaluation import OrderEvaluationService


class OrderServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class OrderService:
    def __init__(
        self,
        execution_engine: PaperExecutionEngine | None = None,
        price_provider: MarketPriceProvider | None = None,
        order_evaluator: OrderEvaluationService | None = None,
    ):
        self.execution_engine = (
            execution_engine or PaperExecutionEngine(price_provider=price_provider)
        )
        self.price_provider = price_provider or market_price_provider
        self.order_evaluator = order_evaluator or OrderEvaluationService(
            execution_engine=self.execution_engine,
            price_provider=self.price_provider,
        )

    def place_order(
        self,
        db: Session,
        *,
        user_id: int,
        stock_symbol: str,
        side: str,
        order_type: str,
        quantity: int,
        limit_price: Decimal | int | float | str | None = None,
        stop_price: Decimal | int | float | str | None = None,
        client_order_id: str | None = None,
    ) -> models.Order:
        try:
            side, order_type, limit_price, stop_price = RiskEngine.validate_terms(
                side=side,
                order_type=order_type,
                quantity=quantity,
                limit_price=limit_price,
                stop_price=stop_price,
            )
        except OrderValidationError as exc:
            raise OrderServiceError(str(exc)) from exc
        symbol = stock_symbol.strip().upper()

        if not symbol:
            raise OrderServiceError("Stock symbol is required")

        try:
            # Serialize all risk decisions for this account before reading
            # purchasing power; never lock a shared Stock row globally.
            wallet = (
                db.query(models.Wallet)
                .filter(
                    models.Wallet.user_id == user_id
                )
                .with_for_update()
                .first()
            )

            user = db.query(models.User).filter(models.User.id == user_id).first()
            try:
                RiskEngine.validate_account(user, wallet)
            except RiskRejected as exc:
                raise OrderServiceError(str(exc), 403 if user is None or not user.is_active else 404) from exc

            stock = (
                db.query(models.Stock)
                .filter(models.Stock.symbol == symbol)
                .first()
            )
            if not stock:
                raise OrderServiceError("Stock not found", 404)

            # -----------------------------
            # Idempotency
            # -----------------------------

            try:
                existing_order = RiskEngine.find_idempotent_order(
                    db,
                    user_id=user_id,
                    client_order_id=client_order_id,
                    symbol=symbol,
                    side=side.value,
                    order_type=order_type.value,
                    quantity=quantity,
                    limit_price=limit_price,
                    stop_price=stop_price,
                )
            except RiskRejected as exc:
                raise OrderServiceError(str(exc), exc.status_code) from exc
            if existing_order is not None:
                db.rollback()
                existing_order.idempotency_replay = True
                return existing_order

            if not stock.is_active:
                raise OrderServiceError("Instrument is not tradable", 409)
            # Use the stored paper quote for both immediate MARKET settlement
            # and first eligibility evaluation of newly accepted resting orders.
            quote = self.price_provider.get_quote(stock)

            # -----------------------------
            # Existing holding
            # -----------------------------

            holding = (
                db.query(models.Holding)
                .filter(
                    models.Holding.user_id == user_id,
                    models.Holding.stock_id == stock.id,
                )
                .with_for_update()
                .first()
            )

            # -----------------------------
            # SELL validation
            # -----------------------------

            # -----------------------------
            # Create order
            # -----------------------------

            order = models.Order(
                user_id=user_id,
                stock_id=stock.id,
                side=side.value,
                order_type=order_type.value,
                status="NEW",
                quantity=quantity,
                filled_quantity=0,
                limit_price=limit_price,
                stop_price=stop_price,
                client_order_id=client_order_id,
            )

            db.add(order)
            db.flush()
            db.add(models.OrderEvent(order_id=order.id, event_type="ORDER_CREATED", metadata_json={
                "source": "order_api",
                "actor": "user",
                "actor_user_id": user_id,
                "side": side.value,
                "order_type": order_type.value,
                "quantity": quantity,
            }))

            transition_order(db, order, "OPEN", event_type="ORDER_OPENED")

            try:
                reservation = RiskEngine.reserve_order(
                    db,
                    order=order,
                    stock=stock,
                    wallet=wallet,
                    holding=holding,
                    quote=quote,
                )
            except RiskRejected as exc:
                raise OrderServiceError(str(exc), 400) from exc

            db.add(models.OrderEvent(
                order_id=order.id,
                event_type="ORDER_ACCEPTED",
                metadata_json={
                    "source": "order_service",
                    "actor": "system",
                    "status": order.status,
                    "quantity": order.quantity,
                    "remaining_quantity": order.remaining_quantity,
                },
            ))

            # -----------------------------
            # MARKET execution
            # -----------------------------

            if order_type is OrderType.MARKET:

                try:
                    self.execution_engine.execute_market(
                        db,
                        order=order,
                        stock=stock,
                        wallet=wallet,
                        holding=holding,
                        reservation=reservation,
                        quote=quote,
                    )
                except ValueError as exc:
                    raise OrderServiceError(
                        str(exc)
                    )

            # Non-market orders are tested against the current stored paper
            # quote once at acceptance. If not eligible, they remain OPEN with
            # their reservation. Future supplied prices use the same evaluator.
            if order_type is not OrderType.MARKET:
                self.order_evaluator.evaluate_open_orders(
                    db,
                    stock_symbol=symbol,
                    current_price=quote.price,
                    order_id=order.id,
                    commit=False,
                )

            db.commit()
            db.refresh(order)

            return order

        except OrderServiceError:
            db.rollback()
            raise

        except Exception:
            db.rollback()
            raise

    def cancel_order(self, db: Session, *, user_id: int, order_id: int) -> models.Order:
        """Cancel an open order and release its unfilled paper assets atomically."""
        try:
            wallet = (
                db.query(models.Wallet)
                .filter(models.Wallet.user_id == user_id)
                .with_for_update()
                .first()
            )
            if wallet is None:
                raise OrderServiceError("Wallet not found", 404)
            order = (
                db.query(models.Order)
                .filter(models.Order.id == order_id)
                .with_for_update()
                .first()
            )
            if order is None:
                raise OrderServiceError("Order not found", 404)
            if order.user_id != user_id:
                raise OrderServiceError("You are not allowed to access this order", 403)
            if order.status not in {"OPEN", "PARTIALLY_FILLED"}:
                raise OrderServiceError(
                    f"Cannot cancel an order in {order.status} state", 409
                )
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
            RiskEngine.release(
                reservation=reservation, wallet=wallet, holding=holding, db=db
            )
            transition_order(db, order, "CANCELLED", event_type="ORDER_CANCELLED")
            db.commit()
            db.refresh(order)
            return order
        except OrderServiceError:
            db.rollback()
            raise
        except InvalidOrderTransition as exc:
            db.rollback()
            raise OrderServiceError(str(exc), 409) from exc
        except Exception:
            db.rollback()
            raise

    def modify_order(
        self,
        db: Session,
        *,
        user_id: int,
        order_id: int,
        changes: dict,
    ) -> models.Order:
        """Modify an unfilled open order while resizing its paper reservation."""
        if not changes:
            raise OrderServiceError("At least one order field must be modified")

        try:
            wallet = (
                db.query(models.Wallet)
                .filter(models.Wallet.user_id == user_id)
                .with_for_update()
                .first()
            )
            if wallet is None:
                raise OrderServiceError("Wallet not found", 404)
            order = (
                db.query(models.Order)
                .filter(models.Order.id == order_id)
                .with_for_update()
                .first()
            )
            if order is None:
                raise OrderServiceError("Order not found", 404)
            if order.user_id != user_id:
                raise OrderServiceError("You are not allowed to access this order", 403)
            if order.status != "OPEN" or order.filled_quantity != 0 or order.stop_triggered:
                raise OrderServiceError(
                    "Only unfilled, untriggered OPEN orders can be modified", 409
                )
            before = {
                "quantity": order.quantity,
                "limit_price": str(order.limit_price) if order.limit_price is not None else None,
                "stop_price": str(order.stop_price) if order.stop_price is not None else None,
            }

            allowed_fields = {
                "MARKET": {"quantity"},
                "LIMIT": {"quantity", "limit_price"},
                "STOP": {"quantity", "stop_price"},
                "STOP_LIMIT": {"quantity", "limit_price", "stop_price"},
            }.get(order.order_type, set())
            unexpected = set(changes) - allowed_fields
            if unexpected:
                raise OrderServiceError(
                    f"Fields cannot be modified for {order.order_type} orders: "
                    + ", ".join(sorted(unexpected))
                )

            quantity = changes.get("quantity", order.quantity)
            limit_price = changes.get("limit_price", order.limit_price)
            stop_price = changes.get("stop_price", order.stop_price)
            try:
                _, _, limit_price, stop_price = RiskEngine.validate_terms(
                    side=order.side,
                    order_type=order.order_type,
                    quantity=quantity,
                    limit_price=limit_price,
                    stop_price=stop_price,
                )
            except OrderValidationError as exc:
                raise OrderServiceError(str(exc)) from exc

            stock = (
                db.query(models.Stock)
                .filter(models.Stock.id == order.stock_id)
                .first()
            )
            if stock is None or not stock.is_active:
                raise OrderServiceError("Instrument is not tradable", 409)
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
            existing_active_reservation = (
                reservation is not None and reservation.state == "ACTIVE"
            )
            prior_reserved_cash = (
                Decimal(reservation.reserved_cash) if reservation is not None else Decimal("0.00")
            )
            prior_reserved_quantity = (
                reservation.reserved_quantity if reservation is not None else 0
            )

            if order.side == "BUY":
                unit_price = (
                    self.price_provider.get_quote(stock).price
                    if order.order_type == OrderType.MARKET.value
                    else Decimal(limit_price if order.order_type in {
                        OrderType.LIMIT.value, OrderType.STOP_LIMIT.value
                    } else stop_price)
                )
                gross_reserve = unit_price * quantity
                desired_cash = gross_reserve + fee_engine.calculate(gross_reserve).total
                if reservation is None or reservation.state != "ACTIVE":
                    if reservation is not None:
                        raise OrderServiceError("Order reservation is not active", 409)
                    order.quantity = quantity
                    order.limit_price = limit_price
                    order.stop_price = stop_price
                    reservation = RiskEngine.reserve_order(
                        db, order=order, stock=stock, wallet=wallet, holding=holding
                    )
                else:
                    delta = desired_cash - Decimal(reservation.reserved_cash)
                    available = Decimal(wallet.balance) - Decimal(wallet.reserved_cash)
                    if delta > available:
                        raise OrderServiceError(
                            f"Insufficient available cash. Available {available}, "
                            f"additional required {delta}"
                        )
                    wallet.reserved_cash = Decimal(wallet.reserved_cash) + delta
                    reservation.reserved_cash = desired_cash
                    reservation.unit_price = unit_price
                    reservation.updated_at = datetime.now(timezone.utc)
                    wallet.updated_at = reservation.updated_at
            else:
                if holding is None:
                    raise OrderServiceError("You do not own this stock", 400)
                desired_shares = quantity
                if reservation is None or reservation.state != "ACTIVE":
                    if reservation is not None:
                        raise OrderServiceError("Order reservation is not active", 409)
                    order.quantity = quantity
                    order.limit_price = limit_price
                    order.stop_price = stop_price
                    reservation = RiskEngine.reserve_order(
                        db, order=order, stock=stock, wallet=wallet, holding=holding
                    )
                else:
                    delta = desired_shares - reservation.reserved_quantity
                    available = holding.quantity - holding.reserved_quantity
                    if delta > available:
                        raise OrderServiceError(
                            f"Insufficient available shares. Available {available}, "
                            f"additional required {delta}"
                        )
                    holding.reserved_quantity += delta
                    reservation.reserved_quantity = desired_shares
                    reservation.updated_at = datetime.now(timezone.utc)
                    holding.updated_at = reservation.updated_at
            order.quantity = quantity
            order.limit_price = limit_price
            order.stop_price = stop_price
            order.updated_at = datetime.now(timezone.utc)
            if existing_active_reservation and (
                prior_reserved_cash != Decimal(reservation.reserved_cash)
                or prior_reserved_quantity != reservation.reserved_quantity
            ):
                AccountingService.record_reservation(
                    db,
                    wallet=wallet,
                    order_id=order.id,
                    event_type="ORDER_RESERVATION",
                    reserved_cash=reservation.reserved_cash - prior_reserved_cash,
                    reserved_quantity=reservation.reserved_quantity - prior_reserved_quantity,
                )
            db.add(models.OrderEvent(
                order_id=order.id,
                event_type="ORDER_MODIFIED",
                metadata_json={
                    "source": "order_api",
                    "actor": "user",
                    "actor_user_id": user_id,
                    "before": before,
                    "after": {
                        "quantity": order.quantity,
                        "limit_price": str(order.limit_price) if order.limit_price is not None else None,
                        "stop_price": str(order.stop_price) if order.stop_price is not None else None,
                    },
                    "changed_fields": sorted(changes),
                },
            ))
            db.commit()
            db.refresh(order)
            return order
        except OrderServiceError:
            db.rollback()
            raise
        except RiskRejected as exc:
            db.rollback()
            raise OrderServiceError(str(exc), exc.status_code) from exc
        except Exception:
            db.rollback()
            raise

    def close_order(
        self, db: Session, *, user_id: int, order_id: int, status: str
    ) -> models.Order:
        """Expire/reject an unfilled or open order and release its remainder."""
        if status not in {"REJECTED", "EXPIRED"}:
            raise OrderServiceError("Unsupported order close status")
        try:
            wallet = (
                db.query(models.Wallet).filter(models.Wallet.user_id == user_id)
                .with_for_update().first()
            )
            if wallet is None:
                raise OrderServiceError("Wallet not found", 404)
            order = (
                db.query(models.Order)
                .filter(models.Order.id == order_id, models.Order.user_id == user_id)
                .with_for_update().first()
            )
            if order is None:
                raise OrderServiceError("Order not found", 404)
            holding = (
                db.query(models.Holding)
                .filter(models.Holding.user_id == user_id, models.Holding.stock_id == order.stock_id)
                .with_for_update().first()
            )
            reservation = (
                db.query(models.OrderReservation)
                .filter(models.OrderReservation.order_id == order.id)
                .with_for_update().first()
            )
            RiskEngine.release(
                reservation=reservation, wallet=wallet, holding=holding, db=db
            )
            transition_order(db, order, status, event_type=f"ORDER_{status}")
            db.commit()
            db.refresh(order)
            return order
        except OrderServiceError:
            db.rollback()
            raise
        except InvalidOrderTransition as exc:
            db.rollback()
            raise OrderServiceError(str(exc), 409) from exc
        except Exception:
            db.rollback()
            raise

    # -----------------------------------------
    # MARKET helper
    # -----------------------------------------

    def place_market_order(
        self,
        db: Session,
        *,
        user_id: int,
        stock_symbol: str,
        side: str,
        quantity: int,
        client_order_id: str | None = None,
    ) -> models.Order:

        return self.place_order(
            db,
            user_id=user_id,
            stock_symbol=stock_symbol,
            side=side,
            order_type="MARKET",
            quantity=quantity,
            client_order_id=client_order_id,
        )

    # -----------------------------------------
    # LIMIT helper
    # -----------------------------------------

    def place_limit_order(
        self,
        db: Session,
        *,
        user_id: int,
        stock_symbol: str,
        side: str,
        quantity: int,
        limit_price: Decimal | int | float | str,
        client_order_id: str | None = None,
    ) -> models.Order:

        return self.place_order(
            db,
            user_id=user_id,
            stock_symbol=stock_symbol,
            side=side,
            order_type="LIMIT",
            quantity=quantity,
            limit_price=limit_price,
            client_order_id=client_order_id,
        )


order_service = OrderService()


def execute_market_order(
    db: Session,
    *,
    user_id: int,
    stock_symbol: str,
    side: str,
    quantity: int,
    client_order_id: str | None = None,
) -> models.Order:

    return order_service.place_market_order(
        db,
        user_id=user_id,
        stock_symbol=stock_symbol,
        side=side,
        quantity=quantity,
        client_order_id=client_order_id,
    )


def create_limit_order(
    db: Session,
    *,
    user_id: int,
    stock_symbol: str,
    side: str,
    quantity: int,
    limit_price: Decimal | int | float | str,
    client_order_id: str | None = None,
) -> models.Order:

    return order_service.place_limit_order(
        db,
        user_id=user_id,
        stock_symbol=stock_symbol,
        side=side,
        quantity=quantity,
        limit_price=limit_price,
        client_order_id=client_order_id,
    )
