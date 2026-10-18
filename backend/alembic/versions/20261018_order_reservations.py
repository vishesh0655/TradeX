"""add transaction-safe paper order reservations

Revision ID: 20261018_order_reservations
Revises: 20261018_order_domain
Create Date: 2026-10-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261018_order_reservations"
down_revision: Union[str, Sequence[str], None] = "20261018_order_domain"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "wallets",
        sa.Column("reserved_cash", sa.Numeric(14, 2), server_default=sa.text("0.00"), nullable=False),
    )
    op.create_check_constraint(
        "wallets_reserved_cash_check", "wallets", "reserved_cash >= 0 AND reserved_cash <= balance"
    )
    op.add_column(
        "holdings",
        sa.Column("reserved_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.create_check_constraint(
        "holdings_reserved_quantity_check",
        "holdings",
        "reserved_quantity >= 0 AND reserved_quantity <= quantity",
    )
    op.create_table(
        "order_reservations",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("order_id", sa.BigInteger(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stock_id", sa.BigInteger(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("reserved_cash", sa.Numeric(14, 2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("reserved_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("state", sa.String(12), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("order_id", name="order_reservations_order_id_key"),
        sa.CheckConstraint("side IN ('BUY', 'SELL')", name="order_reservations_side_check"),
        sa.CheckConstraint("reserved_cash >= 0", name="order_reservations_cash_check"),
        sa.CheckConstraint("reserved_quantity >= 0", name="order_reservations_quantity_check"),
        sa.CheckConstraint("state IN ('ACTIVE', 'RELEASED', 'SETTLED')", name="order_reservations_state_check"),
        sa.CheckConstraint(
            "(side = 'BUY' AND reserved_quantity = 0 AND unit_price IS NOT NULL) OR "
            "(side = 'SELL' AND reserved_cash = 0 AND unit_price IS NULL)",
            name="order_reservations_assets_by_side_check",
        ),
    )
    op.create_index("ix_order_reservations_user_id", "order_reservations", ["user_id"])
    op.create_index("ix_order_reservations_stock_id", "order_reservations", ["stock_id"])


def downgrade() -> None:
    op.drop_index("ix_order_reservations_stock_id", table_name="order_reservations")
    op.drop_index("ix_order_reservations_user_id", table_name="order_reservations")
    op.drop_table("order_reservations")
    op.drop_constraint("holdings_reserved_quantity_check", "holdings", type_="check")
    op.drop_column("holdings", "reserved_quantity")
    op.drop_constraint("wallets_reserved_cash_check", "wallets", type_="check")
    op.drop_column("wallets", "reserved_cash")
