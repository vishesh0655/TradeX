from typing import Literal
from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


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
    side: Literal["BUY", "SELL"]
    order_type: Literal["MARKET", "LIMIT", "STOP", "STOP_LIMIT"] = "MARKET"
    quantity: int = Field(gt=0)
    limit_price: Decimal | None = Field(default=None, gt=0)
    stop_price: Decimal | None = Field(default=None, gt=0)
    client_order_id: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_order_prices(self):
        if self.order_type == "LIMIT" and self.limit_price is None:
            raise ValueError("limit_price is required for LIMIT orders")
        if self.order_type == "STOP" and self.stop_price is None:
            raise ValueError("stop_price is required for STOP orders")
        if self.order_type == "STOP_LIMIT":
            if self.stop_price is None or self.limit_price is None:
                raise ValueError(
                    "stop_price and limit_price are required for STOP_LIMIT orders"
                )
        if self.order_type == "MARKET" and (
            self.limit_price is not None or self.stop_price is not None
        ):
            raise ValueError("MARKET orders cannot include limit_price or stop_price")
        return self


class LegacyOrderCreate(BaseModel):
    stock_symbol: str = Field(min_length=1, max_length=20)
    quantity: int = Field(gt=0)


class OrderOut(BaseModel):
    id: int
    stock_symbol: str
    side: str
    order_type: str
    quantity: int
    filled_quantity: int
    average_fill_price: float | None
    price_per_share: float | None
    total_amount: float | None
    status: str
    client_order_id: str | None = None


class ExecutionOut(BaseModel):
    id: int
    quantity: int
    execution_price: Decimal
    executed_at: datetime
    model_config = ConfigDict(from_attributes=True)


class OrderEventOut(BaseModel):
    id: int
    event_type: str
    metadata_json: dict
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class HoldingOut(BaseModel):
    stock_symbol: str
    company_name: str
    quantity: int
    average_buy_price: float
    current_price: float
    current_value: float
    invested_value: float
    profit_loss: float
    profit_loss_percent: float
