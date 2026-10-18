from decimal import Decimal

from sqlalchemy.orm import Session

from app import models
from app.services.execution_engine import PaperExecutionEngine
from app.services.order_lifecycle import transition_order


class OrderServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class OrderService:
    def __init__(
        self,
        execution_engine: PaperExecutionEngine | None = None,
    ):
        self.execution_engine = (
            execution_engine or PaperExecutionEngine()
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
        limit_price: float | None = None,
        stop_price: float | None = None,
        client_order_id: str | None = None,
    ) -> models.Order:

        side = side.strip().upper()
        order_type = order_type.strip().upper()
        symbol = stock_symbol.strip().upper()

        # -----------------------------
        # Basic validation
        # -----------------------------

        if side not in {"BUY", "SELL"}:
            raise OrderServiceError("Side must be BUY or SELL")

        if order_type not in {
            "MARKET",
            "LIMIT",
            "STOP",
            "STOP_LIMIT",
        }:
            raise OrderServiceError("Unsupported order type")

        if quantity <= 0:
            raise OrderServiceError("Quantity must be positive")

        if not symbol:
            raise OrderServiceError("Stock symbol is required")

        # -----------------------------
        # Price validation
        # -----------------------------

        if order_type == "LIMIT" and limit_price is None:
            raise OrderServiceError(
                "limit_price is required for LIMIT orders"
            )

        if order_type == "STOP" and stop_price is None:
            raise OrderServiceError(
                "stop_price is required for STOP orders"
            )

        if order_type == "STOP_LIMIT":
            if stop_price is None or limit_price is None:
                raise OrderServiceError(
                    "stop_price and limit_price are required "
                    "for STOP_LIMIT orders"
                )

        if order_type == "MARKET":
            if limit_price is not None or stop_price is not None:
                raise OrderServiceError(
                    "MARKET orders cannot include limit_price "
                    "or stop_price"
                )

        try:
            # -----------------------------
            # Find stock
            # -----------------------------

            stock = (
                db.query(models.Stock)
                .filter(
                    models.Stock.symbol == symbol,
                    models.Stock.is_active.is_(True),
                )
                .with_for_update()
                .first()
            )

            if not stock:
                raise OrderServiceError(
                    "Stock not found",
                    404,
                )

            # -----------------------------
            # Wallet
            # -----------------------------

            wallet = (
                db.query(models.Wallet)
                .filter(
                    models.Wallet.user_id == user_id
                )
                .with_for_update()
                .first()
            )

            if not wallet:
                raise OrderServiceError(
                    "Wallet not found",
                    404,
                )

            # -----------------------------
            # Idempotency
            # -----------------------------

            if client_order_id:
                existing_order = (
                    db.query(models.Order)
                    .filter(
                        models.Order.user_id == user_id,
                        models.Order.client_order_id
                        == client_order_id,
                    )
                    .first()
                )

                if existing_order:
                    return existing_order

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

            if side == "SELL":

                if holding is None:
                    raise OrderServiceError(
                        "You do not own this stock"
                    )

                if holding.quantity < quantity:
                    raise OrderServiceError(
                        f"Insufficient shares. "
                        f"You own {holding.quantity} "
                        f"but tried to sell {quantity}"
                    )

            # -----------------------------
            # Create order
            # -----------------------------

            order_status = (
                "NEW"
                if order_type == "MARKET"
                else "OPEN"
            )

            order = models.Order(
                user_id=user_id,
                stock_id=stock.id,
                side=side,
                order_type=order_type,
                status=order_status,
                quantity=quantity,
                filled_quantity=0,
                limit_price=(
                    Decimal(str(limit_price))
                    if limit_price is not None
                    else None
                ),
                stop_price=(
                    Decimal(str(stop_price))
                    if stop_price is not None
                    else None
                ),
                client_order_id=client_order_id,
            )

            db.add(order)
            db.flush()
            db.add(models.OrderEvent(order_id=order.id, event_type="ORDER_CREATED", metadata_json={
                "side": side,
                "order_type": order_type,
                "quantity": quantity,
            }))

            # -----------------------------
            # MARKET execution
            # -----------------------------

            if order_type == "MARKET":

                try:
                    self.execution_engine.execute_market(
                        db,
                        order=order,
                        stock=stock,
                        wallet=wallet,
                        holding=holding,
                    )
                except ValueError as exc:
                    raise OrderServiceError(
                        str(exc)
                    )

            # -----------------------------
            # LIMIT order
            # -----------------------------

            elif order_type == "LIMIT":

                # LIMIT orders are only created here.
                # Matching/execution will be implemented
                # in the next step.
                transition_order(db, order, "OPEN", event_type="ORDER_OPENED")

            # -----------------------------
            # STOP / STOP_LIMIT
            # -----------------------------

            elif order_type in {
                "STOP",
                "STOP_LIMIT",
            }:

                raise OrderServiceError(
                    f"{order_type} orders are not enabled yet"
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
        limit_price: float,
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
    limit_price: float,
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
