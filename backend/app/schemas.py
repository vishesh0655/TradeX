from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.domain.orders import (
    OrderSide,
    OrderStatus,
    OrderType,
    OrderValidationError,
    validate_order_terms,
)


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    wallet_balance: float

    model_config = ConfigDict(from_attributes=True)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class SocialAuthRequest(BaseModel):
    credential: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class OrderCreate(BaseModel):
    stock_symbol: str = Field(min_length=1, max_length=20)
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    quantity: int = Field(strict=True)
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    client_order_id: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_order_prices(self):
        try:
            validate_order_terms(
                side=self.side,
                order_type=self.order_type,
                quantity=self.quantity,
                limit_price=self.limit_price,
                stop_price=self.stop_price,
            )
        except OrderValidationError as exc:
            raise ValueError(str(exc)) from exc
        return self


class OrderModify(BaseModel):
    """Partial update for the mutable terms of an existing paper order."""

    quantity: int | None = Field(default=None, strict=True)
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set:
            raise ValueError("At least one order field must be modified")
        return self


class FeeEstimateRequest(BaseModel):
    side: OrderSide
    gross_notional: Decimal = Field(gt=0)


class FeeEstimateOut(BaseModel):
    side: OrderSide
    gross_notional: Decimal
    brokerage: Decimal
    platform: Decimal
    taxes: Decimal
    total_fees: Decimal
    net_cash_effect: Decimal


class LegacyOrderCreate(BaseModel):
    stock_symbol: str = Field(min_length=1, max_length=20)
    quantity: int = Field(gt=0)


class OrderOut(BaseModel):
    id: int
    stock_symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    filled_quantity: int
    remaining_quantity: int
    average_fill_price: float | None
    price_per_share: float | None
    total_amount: float | None
    status: OrderStatus
    client_order_id: str | None = None
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    stop_triggered: bool = False
    triggered_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ExecutionOut(BaseModel):
    id: int
    execution_ref: str
    quantity: int
    execution_price: Decimal
    gross_notional: Decimal | None = None
    fees: Decimal | None = None
    net_cash_effect: Decimal | None = None
    cost_basis: Decimal | None = None
    realized_pnl: Decimal | None = None
    executed_at: datetime
    model_config = ConfigDict(from_attributes=True)


class OrderEventOut(BaseModel):
    id: int
    event_type: str
    metadata_json: dict
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class WatchlistCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)


class WatchlistOut(BaseModel):
    symbol: str
    company_name: str
    current_price: Decimal
    created_at: datetime


class WalletOut(BaseModel):
    balance: Decimal
    cash_balance: Decimal
    reserved_cash: Decimal
    available_cash: Decimal
    currency: str
    account_type: str = "PAPER"


class WalletTransactionOut(BaseModel):
    id: int
    transaction_type: str
    amount: Decimal
    balance_after: Decimal
    reference_id: int | None
    metadata_json: dict = Field(default_factory=dict)
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class HoldingOut(BaseModel):
    stock_symbol: str
    company_name: str
    quantity: int
    total_quantity: int
    reserved_quantity: int
    available_quantity: int
    average_buy_price: float
    current_price: float
    current_value: float
    market_value: float
    invested_value: float
    profit_loss: float
    profit_loss_percent: float
    unrealized_pnl: float
    unrealized_pnl_percent: float


class PortfolioOut(BaseModel):
    holdings: list[HoldingOut]
    cash_balance: Decimal
    reserved_cash: Decimal
    available_cash: Decimal
    market_value: Decimal
    invested_value: Decimal
    portfolio_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    portfolio_value: Decimal
