"""Average-cost portfolio and unrealized P&L calculations."""

from decimal import Decimal
from decimal import ROUND_HALF_UP

from sqlalchemy.orm import Session

from app import models
from app.services.market_data import (
    MarketPriceProvider,
    MarketQuote,
    market_price_provider,
)


class PortfolioValuationService:
    def __init__(self, price_provider: MarketPriceProvider | None = None):
        self.price_provider = price_provider or market_price_provider

    @staticmethod
    def _realized_pnl(db: Session, *, user_id: int) -> Decimal:
        rows = (
            db.query(models.Execution, models.Order)
            .join(models.Order, models.Order.id == models.Execution.order_id)
            .filter(models.Order.user_id == user_id)
            .order_by(models.Execution.executed_at.asc(), models.Execution.id.asc())
            .all()
        )
        return PortfolioValuationService.calculate_realized_pnl(rows)

    @staticmethod
    def calculate_realized_pnl(rows) -> Decimal:
        positions: dict[tuple[int, int], tuple[int, Decimal]] = {}
        realized_total = Decimal("0.00")
        for execution, order in rows:
            key = (order.user_id, order.stock_id)
            quantity = execution.quantity
            gross = Decimal(
                execution.gross_notional
                if execution.gross_notional is not None
                else Decimal(execution.execution_price) * quantity
            )
            fees = Decimal(execution.fees or 0)
            shares, basis = positions.get(key, (0, Decimal("0.00")))
            if order.side == "BUY":
                acquired_basis = Decimal(
                    execution.cost_basis
                    if execution.cost_basis is not None
                    else gross + fees
                )
                positions[key] = (shares + quantity, basis + acquired_basis)
                continue

            if order.side != "SELL":
                continue
            if shares < quantity:
                # Some legacy holdings may predate execution history. Do not
                # invent a cost basis or realized return for those shares.
                positions.pop(key, None)
                continue
            removed_basis = Decimal(
                execution.cost_basis
                if execution.cost_basis is not None
                else (
                    basis if shares == quantity
                    else (basis * quantity / shares).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                )
            )
            realized = execution.realized_pnl
            if realized is None:
                realized = gross - fees - removed_basis
            realized_total += Decimal(realized)
            positions[key] = (shares - quantity, basis - removed_basis)
        return realized_total

    @staticmethod
    def value_holding(
        holding: models.Holding,
        stock: models.Stock,
        quote: MarketQuote | None = None,
    ) -> dict:
        quantity = holding.quantity
        quote = quote or market_price_provider.get_quote(stock)
        market_value = quote.price * quantity
        invested_value = Decimal(
            getattr(holding, "cost_basis", None)
            or Decimal(holding.average_buy_price) * quantity
        )
        unrealized_pnl = market_value - invested_value
        unrealized_percent = (
            unrealized_pnl / invested_value * Decimal("100")
            if invested_value else Decimal("0")
        )
        return {
            "stock_symbol": stock.symbol,
            "company_name": stock.company_name,
            "quantity": quantity,
            "total_quantity": holding.total_quantity,
            "reserved_quantity": holding.reserved_quantity,
            "available_quantity": holding.available_quantity,
            "average_buy_price": Decimal(holding.average_buy_price),
            "current_price": quote.price,
            "market_value": market_value,
            "current_value": market_value,
            "invested_value": invested_value,
            "unrealized_pnl": unrealized_pnl,
            "profit_loss": unrealized_pnl,
            "unrealized_pnl_percent": unrealized_percent,
            "profit_loss_percent": unrealized_percent,
        }

    def get_portfolio(self, db: Session, *, user_id: int) -> dict:
        wallet = db.query(models.Wallet).filter(
            models.Wallet.user_id == user_id
        ).first()
        if wallet is None:
            raise LookupError("Virtual wallet not found")

        rows = (
            db.query(models.Holding, models.Stock)
            .join(models.Stock, models.Stock.id == models.Holding.stock_id)
            .filter(models.Holding.user_id == user_id)
            .all()
        )
        holdings = [
            self.value_holding(
                holding,
                stock,
                quote=self.price_provider.get_quote(stock),
            )
            for holding, stock in rows
        ]
        market_value = sum((row["market_value"] for row in holdings), Decimal("0"))
        invested_value = sum((row["invested_value"] for row in holdings), Decimal("0"))
        unrealized_pnl = market_value - invested_value
        realized_pnl = PortfolioValuationService._realized_pnl(db, user_id=user_id)
        cash_balance = Decimal(wallet.balance)
        return {
            "holdings": holdings,
            "cash_balance": cash_balance,
            "reserved_cash": Decimal(wallet.reserved_cash),
            "available_cash": Decimal(wallet.available_cash),
            "market_value": market_value,
            "invested_value": invested_value,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "total_pnl": realized_pnl + unrealized_pnl,
            "portfolio_value": cash_balance + market_value,
        }


portfolio_valuation_service = PortfolioValuationService()
