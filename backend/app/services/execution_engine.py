"""Coordinates adapters with transactional fill settlement."""

from sqlalchemy.orm import Session

from app import models
from app.services.execution_adapter import (
    ExecutionAdapter,
    ExecutionFill,
    PaperExecutionAdapter,
)
from app.services.fill_processor import FillProcessor
from app.services.market_data import (
    MarketPriceProvider,
    MarketQuote,
    market_price_provider,
)


class PaperExecutionEngine:
    """Compatibility facade for order execution using the paper adapter."""

    def __init__(
        self,
        adapter: ExecutionAdapter | None = None,
        fill_processor: FillProcessor | None = None,
        price_provider: MarketPriceProvider | None = None,
    ):
        self.adapter = adapter or PaperExecutionAdapter()
        self.fill_processor = fill_processor or FillProcessor()
        self.price_provider = price_provider or market_price_provider
        self.venue = self.adapter.venue

    def execute_market(
        self,
        db: Session,
        *,
        order: models.Order,
        stock: models.Stock,
        wallet: models.Wallet,
        holding: models.Holding | None,
        reservation: models.OrderReservation | None = None,
        quote: MarketQuote | None = None,
    ) -> models.Execution:
        """Compatibility entry point restricted to MARKET orders."""
        if order.order_type != "MARKET":
            raise ValueError("execute_market only accepts MARKET orders")
        return self.execute_eligible_order(
            db,
            order=order,
            stock=stock,
            quote=quote,
            wallet=wallet,
            holding=holding,
            reservation=reservation,
        )

    def execute_eligible_order(
        self,
        db: Session,
        *,
        order: models.Order,
        stock: models.Stock,
        wallet: models.Wallet,
        holding: models.Holding | None,
        reservation: models.OrderReservation | None = None,
        quote: MarketQuote | None = None,
    ) -> models.Execution:
        """Create and settle all adapter-provided fills in one transaction."""
        if reservation is None:
            raise ValueError("An active paper reservation is required to execute")
        executions: list[models.Execution] = []
        try:
            quote = quote or self.price_provider.get_quote(stock)
            if quote.symbol != stock.symbol:
                raise ValueError("Execution quote does not match the order instrument")
            fills = tuple(self.adapter.create_fills(order=order, quote=quote))
            for index, fill in enumerate(fills):
                execution = self.fill_processor.process_fill(
                    db,
                    order=order,
                    stock=stock,
                    wallet=wallet,
                    holding=holding,
                    reservation=reservation,
                    fill=fill,
                )
                executions.append(execution)
                if order.side == "BUY" and holding is None and index < len(fills) - 1:
                    # The processor flushes per fill; re-load the position for
                    # a later fill in the same adapter response.
                    holding = (
                        db.query(models.Holding)
                        .filter(
                            models.Holding.user_id == order.user_id,
                            models.Holding.stock_id == stock.id,
                        )
                        .with_for_update()
                        .first()
                    )
            if not executions:
                raise ValueError("Execution adapter returned no fills for MARKET order")
            return executions[-1]
        except Exception:
            db.rollback()
            raise

    def execute_fill(
        self, db: Session, *, order_id: int, fill: ExecutionFill
    ) -> models.Execution:
        """Settle an individual externally supplied paper fill under row locks."""
        return self.fill_processor.execute_fill(db, order_id=order_id, fill=fill)
