from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str

    class Config:
        from_attributes = True
class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
class OrderCreate(BaseModel):
    stock_symbol: str
    quantity: int


class OrderOut(BaseModel):
    id: int
    stock_id: int
    order_type: str
    quantity: int
    price_per_share: float
    total_amount: float
    status: str

    class Config:
        from_attributes = True
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