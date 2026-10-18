"""Order value types and validation shared by schemas and services."""

from decimal import Decimal, InvalidOperation
from enum import StrEnum

MAX_ORDER_QUANTITY = 2_147_483_647
MAX_NUMERIC_14_2 = Decimal("999999999999.99")


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(StrEnum):
    NEW = "NEW"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class OrderValidationError(ValueError):
    """Raised when order terms violate the paper-trading contract."""


def _positive_decimal(value: Decimal | int | float | str | None, name: str) -> Decimal | None:
    if value is None:
        return None
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise OrderValidationError(f"{name} must be a positive number") from exc
    if not amount.is_finite() or amount <= 0:
        raise OrderValidationError(f"{name} must be a positive number")
    try:
        fits_numeric = amount <= MAX_NUMERIC_14_2 and amount == amount.quantize(Decimal("0.01"))
    except InvalidOperation:
        fits_numeric = False
    if not fits_numeric:
        raise OrderValidationError(
            f"{name} must fit the supported precision (up to 12 integer and 2 decimal places)"
        )
    return amount


def validate_order_terms(
    *,
    side: str,
    order_type: str,
    quantity: int,
    limit_price: Decimal | int | float | str | None = None,
    stop_price: Decimal | int | float | str | None = None,
) -> tuple[OrderSide, OrderType, Decimal | None, Decimal | None]:
    """Normalize and validate order terms for both API and internal callers."""
    try:
        normalized_side = OrderSide(str(side).strip().upper())
    except ValueError as exc:
        raise OrderValidationError("Side must be BUY or SELL") from exc

    try:
        normalized_type = OrderType(str(order_type).strip().upper())
    except ValueError as exc:
        raise OrderValidationError("Unsupported order type") from exc

    if (
        isinstance(quantity, bool)
        or not isinstance(quantity, int)
        or quantity <= 0
        or quantity > MAX_ORDER_QUANTITY
    ):
        raise OrderValidationError("Quantity must be a positive whole number within the supported range")

    normalized_limit = _positive_decimal(limit_price, "limit_price")
    normalized_stop = _positive_decimal(stop_price, "stop_price")

    if normalized_type is OrderType.MARKET:
        if normalized_limit is not None or normalized_stop is not None:
            raise OrderValidationError("MARKET orders cannot include limit_price or stop_price")
    elif normalized_type is OrderType.LIMIT:
        if normalized_limit is None:
            raise OrderValidationError("limit_price is required for LIMIT orders")
        if normalized_stop is not None:
            raise OrderValidationError("LIMIT orders cannot include stop_price")
    elif normalized_type is OrderType.STOP:
        if normalized_stop is None:
            raise OrderValidationError("stop_price is required for STOP orders")
        if normalized_limit is not None:
            raise OrderValidationError("STOP orders cannot include limit_price")
    elif normalized_type is OrderType.STOP_LIMIT:
        if normalized_stop is None or normalized_limit is None:
            raise OrderValidationError(
                "stop_price and limit_price are required for STOP_LIMIT orders"
            )

    return normalized_side, normalized_type, normalized_limit, normalized_stop


def validate_fill_quantities(quantity: int, filled_quantity: int) -> None:
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise OrderValidationError("Order quantity must be a positive whole number")
    if (
        isinstance(filled_quantity, bool)
        or not isinstance(filled_quantity, int)
        or filled_quantity < 0
        or filled_quantity > quantity
        or quantity > MAX_ORDER_QUANTITY
    ):
        raise OrderValidationError("Filled quantity must be between zero and order quantity")
