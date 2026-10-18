"""Central order state transition rules for the paper trading lifecycle."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import models


ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "NEW": frozenset({"OPEN", "FILLED", "REJECTED"}),
    "OPEN": frozenset({"PARTIALLY_FILLED", "FILLED", "CANCEL_PENDING", "CANCELLED", "EXPIRED"}),
    "PARTIALLY_FILLED": frozenset({"FILLED", "CANCEL_PENDING", "CANCELLED", "EXPIRED"}),
    "CANCEL_PENDING": frozenset({"CANCELLED"}),
    "FILLED": frozenset(),
    "CANCELLED": frozenset(),
    "REJECTED": frozenset(),
    "EXPIRED": frozenset(),
}


class InvalidOrderTransition(ValueError):
    pass


def transition_order(
    db: Session,
    order: models.Order,
    new_status: str,
    *,
    event_type: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Apply one permitted transition and append its immutable audit event."""
    old_status = order.status
    if new_status not in ALLOWED_TRANSITIONS.get(old_status, frozenset()):
        raise InvalidOrderTransition(
            f"Cannot transition order from {old_status} to {new_status}"
        )

    order.status = new_status
    order.updated_at = datetime.now(timezone.utc)
    db.add(
        models.OrderEvent(
            order_id=order.id,
            event_type=event_type or f"ORDER_{new_status}",
            metadata_json={"from": old_status, "to": new_status, **(metadata or {})},
        )
    )
