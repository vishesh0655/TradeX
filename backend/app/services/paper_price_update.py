"""Persist trusted paper quotes and evaluate resting paper orders atomically."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app import models
from app.services.order_evaluation import (
    EvaluationReport,
    OrderEvaluationService,
    order_evaluation_service,
)


class PaperPriceUpdateError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class PaperPriceUpdateService:
    """Accept a supplied quote; this service does not create or source prices."""

    def __init__(self, evaluator: OrderEvaluationService | None = None):
        self.evaluator = evaluator or order_evaluation_service

    def update_price(
        self,
        db: Session,
        *,
        symbol: str,
        price: Decimal | int | float | str,
    ) -> dict:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise PaperPriceUpdateError("Instrument symbol is required")
        try:
            normalized_price = (
                price if isinstance(price, Decimal) else Decimal(str(price))
            )
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise PaperPriceUpdateError("Price must be a positive amount") from exc
        if (
            not normalized_price.is_finite()
            or normalized_price <= 0
            or normalized_price > Decimal("999999999999.99")
            or normalized_price != normalized_price.quantize(Decimal("0.01"))
        ):
            raise PaperPriceUpdateError(
                "Price must be positive and support no more than two decimal places"
            )

        try:
            stock = (
                db.query(models.Stock)
                .filter(models.Stock.symbol == normalized_symbol)
                .with_for_update()
                .first()
            )
            if stock is None:
                raise PaperPriceUpdateError("Instrument not found", 404)
            if not stock.is_active:
                raise PaperPriceUpdateError("Instrument is not tradable", 409)

            previous_price = Decimal(stock.current_price)
            stock.current_price = normalized_price
            stock.updated_at = datetime.now(timezone.utc)
            db.flush()

            report: EvaluationReport = self.evaluator.evaluate_open_orders(
                db,
                stock_symbol=normalized_symbol,
                current_price=normalized_price,
                commit=False,
            )
            db.commit()
            return {
                "symbol": normalized_symbol,
                "previous_price": previous_price,
                "price": normalized_price,
                "updated_at": stock.updated_at,
                "orders_evaluated": report.orders_evaluated,
                "stop_orders_triggered": report.stop_orders_triggered,
                "orders_filled": report.orders_filled,
                "orders_partially_filled": report.orders_partially_filled,
                "orders_rejected": report.orders_rejected,
            }
        except PaperPriceUpdateError:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            raise PaperPriceUpdateError("Paper price update failed", 500) from exc


paper_price_update_service = PaperPriceUpdateService()
