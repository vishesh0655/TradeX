from sqlalchemy import (
    Column,
    BigInteger,
    Integer,
    String,
    Boolean,
    Numeric,
    CHAR,
    TIMESTAMP,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
    Computed,
    text,
)
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    wallet = relationship("Wallet", back_populates="user", uselist=False)
    orders = relationship("Order", back_populates="user")
    holdings = relationship("Holding", back_populates="user")


class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    balance = Column(Numeric(14, 2), nullable=False, server_default=text("1000000.00"))
    currency = Column(CHAR(3), nullable=False, server_default=text("'INR'"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        CheckConstraint("balance >= 0", name="wallets_balance_check"),
    )

    user = relationship("User", back_populates="wallet")


class Stock(Base):
    __tablename__ = "stocks"

    id = Column(BigInteger, primary_key=True)
    symbol = Column(String(20), nullable=False, unique=True)
    company_name = Column(String(255), nullable=False)
    exchange = Column(String(20), nullable=False, server_default=text("'NSE'"))
    current_price = Column(Numeric(14, 2), nullable=False)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        CheckConstraint("current_price > 0", name="stocks_current_price_check"),
    )

    orders = relationship("Order", back_populates="stock")
    holdings = relationship("Holding", back_populates="stock")


class Order(Base):
    __tablename__ = "orders"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    stock_id = Column(BigInteger, ForeignKey("stocks.id"), nullable=False)
    order_type = Column(String(4), nullable=False)
    quantity = Column(Integer, nullable=False)
    price_per_share = Column(Numeric(14, 2), nullable=False)
    total_amount = Column(
        Numeric(16, 2),
        Computed("(quantity::numeric * price_per_share)", persisted=True),
    )
    status = Column(String(20), nullable=False, server_default=text("'COMPLETED'"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    executed_at = Column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("order_type IN ('BUY', 'SELL')", name="orders_order_type_check"),
        CheckConstraint("price_per_share > 0", name="orders_price_per_share_check"),
        CheckConstraint("quantity > 0", name="orders_quantity_check"),
        CheckConstraint("status IN ('PENDING', 'COMPLETED', 'REJECTED')", name="orders_status_check"),
    )

    user = relationship("User", back_populates="orders")
    stock = relationship("Stock", back_populates="orders")


class Holding(Base):
    __tablename__ = "holdings"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    stock_id = Column(BigInteger, ForeignKey("stocks.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    average_buy_price = Column(Numeric(14, 2), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        UniqueConstraint("user_id", "stock_id", name="holdings_user_id_stock_id_key"),
        CheckConstraint("average_buy_price > 0", name="holdings_average_buy_price_check"),
        CheckConstraint("quantity > 0", name="holdings_quantity_check"),
    )

    user = relationship("User", back_populates="holdings")
    stock = relationship("Stock", back_populates="holdings")