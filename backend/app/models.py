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
    text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=True)

    is_active = Column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )

    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    wallet = relationship(
        "Wallet",
        back_populates="user",
        uselist=False,
    )

    orders = relationship(
        "Order",
        back_populates="user",
    )

    holdings = relationship(
        "Holding",
        back_populates="user",
    )

    identities = relationship(
        "UserIdentity",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserIdentity(Base):
    __tablename__ = "user_identities"

    id = Column(BigInteger, primary_key=True)

    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    provider = Column(
        String(20),
        nullable=False,
    )

    provider_subject = Column(
        String(255),
        nullable=False,
    )

    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_subject",
            name="user_identities_provider_subject_key",
        ),
    )

    user = relationship(
        "User",
        back_populates="identities",
    )


class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(BigInteger, primary_key=True)

    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    balance = Column(
        Numeric(14, 2),
        nullable=False,
        server_default=text("1000000.00"),
    )

    currency = Column(
        CHAR(3),
        nullable=False,
        server_default=text("'INR'"),
    )

    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    updated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        CheckConstraint(
            "balance >= 0",
            name="wallets_balance_check",
        ),
    )

    user = relationship(
        "User",
        back_populates="wallet",
    )

    transactions = relationship(
        "WalletTransaction",
        back_populates="wallet",
        cascade="all, delete-orphan",
    )


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id = Column(BigInteger, primary_key=True)

    wallet_id = Column(
        BigInteger,
        ForeignKey("wallets.id", ondelete="CASCADE"),
        nullable=False,
    )

    transaction_type = Column(
        String(30),
        nullable=False,
    )

    amount = Column(
        Numeric(14, 2),
        nullable=False,
    )

    balance_after = Column(
        Numeric(14, 2),
        nullable=False,
    )

    reference_id = Column(
        BigInteger,
        ForeignKey("orders.id"),
        nullable=True,
    )

    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    wallet = relationship(
        "Wallet",
        back_populates="transactions",
    )

    order = relationship(
        "Order",
        foreign_keys=[reference_id],
    )


class Stock(Base):
    __tablename__ = "stocks"

    id = Column(BigInteger, primary_key=True)

    symbol = Column(
        String(20),
        nullable=False,
        unique=True,
    )

    company_name = Column(
        String(255),
        nullable=False,
    )

    exchange = Column(
        String(20),
        nullable=False,
        server_default=text("'NSE'"),
    )

    current_price = Column(
        Numeric(14, 2),
        nullable=False,
    )

    is_active = Column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )

    updated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        CheckConstraint(
            "current_price > 0",
            name="stocks_current_price_check",
        ),
    )

    orders = relationship(
        "Order",
        back_populates="stock",
    )

    holdings = relationship(
        "Holding",
        back_populates="stock",
    )


class Order(Base):
    __tablename__ = "orders"

    id = Column(
        BigInteger,
        primary_key=True,
    )

    user_id = Column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=False,
    )

    stock_id = Column(
        BigInteger,
        ForeignKey("stocks.id"),
        nullable=False,
    )

    # BUY or SELL
    side = Column(
        String(4),
        nullable=False,
    )

    # MARKET, LIMIT, STOP, STOP_LIMIT
    order_type = Column(
        String(10),
        nullable=False,
    )

    # NEW, OPEN, PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED
    status = Column(
        String(20),
        nullable=False,
        server_default=text("'NEW'"),
    )

    quantity = Column(
        Integer,
        nullable=False,
    )

    filled_quantity = Column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    limit_price = Column(
        Numeric(14, 2),
        nullable=True,
    )

    stop_price = Column(
        Numeric(14, 2),
        nullable=True,
    )

    average_fill_price = Column(
        Numeric(14, 2),
        nullable=True,
    )

    client_order_id = Column(
        String(100),
        nullable=True,
    )

    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    updated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        CheckConstraint(
            "side IN ('BUY', 'SELL')",
            name="orders_side_check",
        ),

        CheckConstraint(
            "order_type IN ('MARKET', 'LIMIT', 'STOP', 'STOP_LIMIT')",
            name="orders_order_type_check",
        ),

        CheckConstraint(
            "status IN ("
            "'NEW', "
            "'OPEN', "
            "'PARTIALLY_FILLED', "
            "'FILLED', "
            "'CANCELLED', "
            "'CANCEL_PENDING', "
            "'REJECTED', "
            "'EXPIRED'"
            ")",
            name="orders_status_check",
        ),

        CheckConstraint(
            "quantity > 0",
            name="orders_quantity_check",
        ),

        CheckConstraint(
            "filled_quantity >= 0",
            name="orders_filled_quantity_check",
        ),

        CheckConstraint(
            "filled_quantity <= quantity",
            name="orders_filled_quantity_limit_check",
        ),

        CheckConstraint(
            "limit_price IS NULL OR limit_price > 0",
            name="orders_limit_price_check",
        ),

        CheckConstraint(
            "stop_price IS NULL OR stop_price > 0",
            name="orders_stop_price_check",
        ),

        UniqueConstraint(
            "user_id",
            "client_order_id",
            name="orders_user_client_order_id_key",
        ),
    )

    user = relationship(
        "User",
        back_populates="orders",
    )

    stock = relationship(
        "Stock",
        back_populates="orders",
    )

    executions = relationship(
        "Execution",
        back_populates="order",
        cascade="all, delete-orphan",
    )

    events = relationship(
        "OrderEvent",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderEvent.created_at",
    )


class OrderEvent(Base):
    """Append-only application audit event for an order lifecycle change."""

    __tablename__ = "order_events"

    id = Column(BigInteger, primary_key=True)
    order_id = Column(
        BigInteger,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type = Column(String(40), nullable=False)
    metadata_json = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    order = relationship("Order", back_populates="events")


class Execution(Base):
    __tablename__ = "executions"

    id = Column(
        BigInteger,
        primary_key=True,
    )

    order_id = Column(
        BigInteger,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    quantity = Column(
        Integer,
        nullable=False,
    )

    execution_price = Column(
        Numeric(14, 2),
        nullable=False,
    )

    executed_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        CheckConstraint(
            "quantity > 0",
            name="executions_quantity_check",
        ),

        CheckConstraint(
            "execution_price > 0",
            name="executions_price_check",
        ),
    )

    order = relationship(
        "Order",
        back_populates="executions",
    )


class Holding(Base):
    __tablename__ = "holdings"

    id = Column(
        BigInteger,
        primary_key=True,
    )

    user_id = Column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=False,
    )

    stock_id = Column(
        BigInteger,
        ForeignKey("stocks.id"),
        nullable=False,
    )

    quantity = Column(
        Integer,
        nullable=False,
    )

    average_buy_price = Column(
        Numeric(14, 2),
        nullable=False,
    )

    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    updated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "stock_id",
            name="holdings_user_id_stock_id_key",
        ),

        CheckConstraint(
            "average_buy_price > 0",
            name="holdings_average_buy_price_check",
        ),

        CheckConstraint(
            "quantity > 0",
            name="holdings_quantity_check",
        ),
    )

    user = relationship(
        "User",
        back_populates="holdings",
    )

    stock = relationship(
        "Stock",
        back_populates="holdings",
    )
