"""Central order state transition rules for the paper trading lifecycle."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import models
from app.domain.orders import OrderStatus, OrderValidationError, validate_fill_quantities


ALLOWED_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.NEW: frozenset({OrderStatus.OPEN, OrderStatus.REJECTED}),
    OrderStatus.OPEN: frozenset({
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCEL_PENDING,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
    }),
    OrderStatus.PARTIALLY_FILLED: frozenset({
        OrderStatus.FILLED,
        OrderStatus.CANCEL_PENDING,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
        OrderStatus.EXPIRED,
    }),
    OrderStatus.CANCEL_PENDING: frozenset({OrderStatus.CANCELLED}),
    OrderStatus.FILLED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.REJECTED: frozenset(),
    OrderStatus.EXPIRED: frozenset(),
}


class InvalidOrderTransition(ValueError):
    pass


def transition_order(
    db: Session,
    order: models.Order,
    new_status: str | OrderStatus,
    *,
    event_type: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Apply one permitted transition and append its immutable audit event."""
    try:
        old_status = OrderStatus(order.status)
        target_status = OrderStatus(new_status)
    except ValueError as exc:
        raise InvalidOrderTransition("Unknown order status") from exc

    try:
        validate_fill_quantities(order.quantity, order.filled_quantity)
    except OrderValidationError as exc:
        raise InvalidOrderTransition(str(exc)) from exc

    if target_status not in ALLOWED_TRANSITIONS[old_status]:
        raise InvalidOrderTransition(
            f"Cannot transition order from {old_status.value} to {target_status.value}"
        )

    if target_status is OrderStatus.PARTIALLY_FILLED and not (
        0 < order.filled_quantity < order.quantity
    ):
        raise InvalidOrderTransition(
            "PARTIALLY_FILLED orders must have a fill below the order quantity"
        )
    if target_status is OrderStatus.FILLED and order.filled_quantity != order.quantity:
        raise InvalidOrderTransition("FILLED orders must have the full order quantity filled")

    order.status = target_status.value
    order.updated_at = datetime.now(timezone.utc)
    event_metadata = dict(metadata or {})
    event_metadata.pop("from", None)
    event_metadata.pop("to", None)
    db.add(
        models.OrderEvent(
            order_id=order.id,
            event_type=event_type or f"ORDER_{target_status.value}",
            metadata_json={
                "from": old_status.value,
                "source": "order_lifecycle",
                "actor": "system",
                **event_metadata,
                "to": target_status.value,
            },
        )
    )
