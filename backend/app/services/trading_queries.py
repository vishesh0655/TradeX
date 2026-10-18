"""Read and account scoped query operations for the paper trading API."""

from datetime import datetime

from sqlalchemy.orm import Session

from app import models
from app.services.portfolio_valuation import portfolio_valuation_service


class TradingQueryError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class TradingQueryService:
    """Contains account scoping, filters, and pagination for trading reads."""

    ORDER_STATUSES = {
        "NEW", "OPEN", "PARTIALLY_FILLED", "FILLED", "CANCEL_PENDING",
        "CANCELLED", "REJECTED", "EXPIRED",
    }
    ORDER_SIDES = {"BUY", "SELL"}
    ORDER_TYPES = {"MARKET", "LIMIT", "STOP", "STOP_LIMIT"}

    @staticmethod
    def _validate_page(limit: int, offset: int) -> None:
        if not 1 <= limit <= 100 or offset < 0:
            raise TradingQueryError("limit must be between 1 and 100 and offset must be non-negative")

    @staticmethod
    def _validate_date_range(start: datetime | None, end: datetime | None) -> None:
        if start is not None and end is not None and (start.tzinfo is None) != (end.tzinfo is None):
            raise TradingQueryError("Start and end dates must use the same timezone format")
        if start is not None and end is not None and start > end:
            raise TradingQueryError("Start date must be earlier than or equal to end date")

    def list_stocks(
        self, db: Session, *, limit: int, offset: int, search: str | None = None
    ) -> tuple[list[models.Stock], int]:
        self._validate_page(limit, offset)
        query = db.query(models.Stock).filter(models.Stock.is_active.is_(True))
        if search:
            pattern = f"%{search.strip()}%"
            query = query.filter(
                models.Stock.symbol.ilike(pattern)
                | models.Stock.company_name.ilike(pattern)
            )
        total = query.count()
        rows = query.order_by(models.Stock.symbol).offset(offset).limit(limit).all()
        return rows, total

    @staticmethod
    def get_quote(db: Session, *, symbol: str) -> models.Stock:
        row = (
            db.query(models.Stock)
            .filter(
                models.Stock.symbol == symbol.strip().upper(),
                models.Stock.is_active.is_(True),
            )
            .first()
        )
        if row is None:
            raise TradingQueryError("Stock not found", 404)
        return row

    @staticmethod
    def get_wallet(db: Session, *, user_id: int) -> models.Wallet:
        wallet = db.query(models.Wallet).filter(models.Wallet.user_id == user_id).first()
        if wallet is None:
            raise TradingQueryError("Virtual wallet not found", 404)
        return wallet

    def get_wallet_summary(self, db: Session, *, user_id: int) -> dict:
        wallet = self.get_wallet(db, user_id=user_id)
        return {
            "balance": wallet.available_cash,
            "cash_balance": wallet.balance,
            "reserved_cash": wallet.reserved_cash,
            "available_cash": wallet.available_cash,
            "currency": wallet.currency,
        }

    @staticmethod
    def get_user_summary(user: models.User) -> dict:
        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "wallet_balance": float(user.wallet.available_cash),
        }

    def list_wallet_transactions(
        self, db: Session, *, user_id: int, limit: int, offset: int,
        transaction_type: str | None = None, created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> tuple[list[models.WalletTransaction], int]:
        self._validate_page(limit, offset)
        self._validate_date_range(created_from, created_to)
        wallet = self.get_wallet(db, user_id=user_id)
        query = db.query(models.WalletTransaction).filter(
            models.WalletTransaction.wallet_id == wallet.id
        )
        if transaction_type:
            query = query.filter(models.WalletTransaction.transaction_type == transaction_type.upper())
        if created_from:
            query = query.filter(models.WalletTransaction.created_at >= created_from)
        if created_to:
            query = query.filter(models.WalletTransaction.created_at <= created_to)
        total = query.count()
        rows = query.order_by(
            models.WalletTransaction.created_at.desc(), models.WalletTransaction.id.desc()
        ).offset(offset).limit(limit).all()
        return rows, total

    def list_orders(
        self, db: Session, *, user_id: int, limit: int, offset: int,
        status: str | None = None, symbol: str | None = None, side: str | None = None,
        order_type: str | None = None, created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> tuple[list[models.Order], int]:
        self._validate_page(limit, offset)
        self._validate_date_range(created_from, created_to)
        if status and status.upper() not in self.ORDER_STATUSES:
            raise TradingQueryError("Unsupported order status filter")
        if side and side.upper() not in self.ORDER_SIDES:
            raise TradingQueryError("Unsupported order side filter")
        if order_type and order_type.upper() not in self.ORDER_TYPES:
            raise TradingQueryError("Unsupported order type filter")
        query = db.query(models.Order).join(models.Stock).filter(models.Order.user_id == user_id)
        if status:
            query = query.filter(models.Order.status == status.upper())
        if symbol:
            query = query.filter(models.Stock.symbol == symbol.strip().upper())
        if side:
            query = query.filter(models.Order.side == side.upper())
        if order_type:
            query = query.filter(models.Order.order_type == order_type.upper())
        if created_from:
            query = query.filter(models.Order.created_at >= created_from)
        if created_to:
            query = query.filter(models.Order.created_at <= created_to)
        total = query.count()
        rows = query.order_by(models.Order.created_at.desc(), models.Order.id.desc()).offset(offset).limit(limit).all()
        return rows, total

    @staticmethod
    def get_order(db: Session, *, user_id: int, order_id: int) -> models.Order:
        order = db.query(models.Order).filter(models.Order.id == order_id).first()
        if order is None:
            raise TradingQueryError("Order not found", 404)
        if order.user_id != user_id:
            raise TradingQueryError("You are not allowed to access this order", 403)
        return order

    def list_executions(
        self, db: Session, *, user_id: int, order_id: int, limit: int, offset: int,
        executed_from: datetime | None = None, executed_to: datetime | None = None,
    ) -> tuple[list[models.Execution], int]:
        self._validate_page(limit, offset)
        self._validate_date_range(executed_from, executed_to)
        self.get_order(db, user_id=user_id, order_id=order_id)
        query = db.query(models.Execution).filter(models.Execution.order_id == order_id)
        if executed_from:
            query = query.filter(models.Execution.executed_at >= executed_from)
        if executed_to:
            query = query.filter(models.Execution.executed_at <= executed_to)
        total = query.count()
        rows = query.order_by(models.Execution.executed_at.asc(), models.Execution.id.asc()).offset(offset).limit(limit).all()
        return rows, total

    def list_order_events(
        self, db: Session, *, user_id: int, order_id: int, limit: int, offset: int,
        event_type: str | None = None, created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> tuple[list[models.OrderEvent], int]:
        self._validate_page(limit, offset)
        self._validate_date_range(created_from, created_to)
        self.get_order(db, user_id=user_id, order_id=order_id)
        query = db.query(models.OrderEvent).filter(models.OrderEvent.order_id == order_id)
        if event_type:
            query = query.filter(models.OrderEvent.event_type == event_type.upper())
        if created_from:
            query = query.filter(models.OrderEvent.created_at >= created_from)
        if created_to:
            query = query.filter(models.OrderEvent.created_at <= created_to)
        total = query.count()
        rows = query.order_by(models.OrderEvent.created_at.asc(), models.OrderEvent.id.asc()).offset(offset).limit(limit).all()
        return rows, total

    @staticmethod
    def get_holdings(db: Session, *, user_id: int) -> list[dict]:
        portfolio = portfolio_valuation_service.get_portfolio(db, user_id=user_id)
        return portfolio["holdings"]

    @staticmethod
    def list_watchlist(db: Session, *, user_id: int) -> list[tuple[models.WatchlistItem, models.Stock]]:
        return (
            db.query(models.WatchlistItem, models.Stock)
            .join(models.Stock, models.Stock.id == models.WatchlistItem.stock_id)
            .filter(models.WatchlistItem.user_id == user_id)
            .order_by(models.WatchlistItem.created_at.desc(), models.WatchlistItem.id.desc())
            .all()
        )

    @staticmethod
    def add_watchlist_item(db: Session, *, user_id: int, symbol: str) -> tuple[models.WatchlistItem, models.Stock]:
        stock = (
            db.query(models.Stock)
            .filter(models.Stock.symbol == symbol.strip().upper(), models.Stock.is_active.is_(True))
            .first()
        )
        if stock is None:
            raise TradingQueryError("Stock not found", 404)
        item = (
            db.query(models.WatchlistItem)
            .filter(models.WatchlistItem.user_id == user_id, models.WatchlistItem.stock_id == stock.id)
            .first()
        )
        if item is None:
            item = models.WatchlistItem(user_id=user_id, stock_id=stock.id)
            db.add(item)
            db.commit()
            db.refresh(item)
        return item, stock

    @staticmethod
    def remove_watchlist_item(db: Session, *, user_id: int, symbol: str) -> None:
        item = (
            db.query(models.WatchlistItem)
            .join(models.Stock, models.Stock.id == models.WatchlistItem.stock_id)
            .filter(
                models.WatchlistItem.user_id == user_id,
                models.Stock.symbol == symbol.strip().upper(),
            )
            .first()
        )
        if item is None:
            raise TradingQueryError("Watchlist item not found", 404)
        db.delete(item)
        db.commit()


trading_query_service = TradingQueryService()
