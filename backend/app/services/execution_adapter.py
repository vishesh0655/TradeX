"""Execution venue contracts and the local paper-only implementation."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence
from uuid import uuid4

from app import models
from app.services.market_data import MarketQuote


@dataclass(frozen=True)
class ExecutionFill:
    execution_ref: str
    quantity: int
    execution_price: Decimal
    executed_at: datetime | None = None


class ExecutionAdapter(Protocol):
    """Produces fills for accepted orders; it never settles account state."""

    venue: str

    def create_fills(
        self, *, order: models.Order, quote: MarketQuote
    ) -> Sequence[ExecutionFill]: ...


class PaperExecutionAdapter:
    """Fills MARKET orders from the stock price already stored in TradeX."""

    venue = "PAPER"

    def __init__(self, max_fill_quantity: int | None = None):
        if max_fill_quantity is not None and max_fill_quantity <= 0:
            raise ValueError("max_fill_quantity must be positive")
        self.max_fill_quantity = max_fill_quantity

    def create_fills(
        self, *, order: models.Order, quote: MarketQuote
    ) -> Sequence[ExecutionFill]:
        if order.order_type in {"STOP", "STOP_LIMIT"} and not order.stop_triggered:
            return ()
        if order.order_type not in {"MARKET", "LIMIT", "STOP", "STOP_LIMIT"}:
            return ()
        quantity = order.remaining_quantity
        if self.max_fill_quantity is not None:
            quantity = min(quantity, self.max_fill_quantity)
        return (
            ExecutionFill(
                execution_ref=f"PAPER-{uuid4().hex}",
                quantity=quantity,
                execution_price=quote.price,
            ),
        )
