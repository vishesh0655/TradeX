"""redesign orders and add executions

Revision ID: 48037e0cb146
Revises: bd7b747df8c6
Create Date: 2026-10-18 11:06:43.398195

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "48037e0cb146"
down_revision: Union[str, Sequence[str], None] = "bd7b747df8c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================
    # 1. Add side temporarily as nullable
    # =========================================================

    op.add_column(
        "orders",
        sa.Column(
            "side",
            sa.String(length=4),
            nullable=True,
        ),
    )

    # =========================================================
    # 2. Remove OLD constraints before changing old values
    #
    # Old order_type constraint expects:
    #   BUY / SELL
    #
    # Old status constraint expects:
    #   PENDING / COMPLETED / REJECTED
    # =========================================================

    op.drop_constraint(
        "orders_order_type_check",
        "orders",
        type_="check",
    )

    op.drop_constraint(
        "orders_status_check",
        "orders",
        type_="check",
    )

    # =========================================================
    # 3. Copy old BUY / SELL values into side
    # =========================================================

    op.execute(
        """
        UPDATE orders
        SET side = order_type
        WHERE order_type IN ('BUY', 'SELL')
        """
    )

    # =========================================================
    # 4. Change order_type VARCHAR(4) -> VARCHAR(10)
    # =========================================================

    op.alter_column(
        "orders",
        "order_type",
        existing_type=sa.VARCHAR(length=4),
        type_=sa.String(length=10),
        existing_nullable=False,
    )

    # =========================================================
    # 5. Convert old BUY / SELL order_type to MARKET
    # =========================================================

    op.execute(
        """
        UPDATE orders
        SET order_type = 'MARKET'
        WHERE order_type IN ('BUY', 'SELL')
        """
    )

    # =========================================================
    # 6. Add new order fields
    # =========================================================

    op.add_column(
        "orders",
        sa.Column(
            "filled_quantity",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )

    op.add_column(
        "orders",
        sa.Column(
            "limit_price",
            sa.Numeric(
                precision=14,
                scale=2,
            ),
            nullable=True,
        ),
    )

    op.add_column(
        "orders",
        sa.Column(
            "stop_price",
            sa.Numeric(
                precision=14,
                scale=2,
            ),
            nullable=True,
        ),
    )

    op.add_column(
        "orders",
        sa.Column(
            "average_fill_price",
            sa.Numeric(
                precision=14,
                scale=2,
            ),
            nullable=True,
        ),
    )

    op.add_column(
        "orders",
        sa.Column(
            "client_order_id",
            sa.String(length=100),
            nullable=True,
        ),
    )

    op.add_column(
        "orders",
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )

    # =========================================================
    # 7. Convert old statuses
    #
    # PENDING   -> OPEN
    # COMPLETED -> FILLED
    # REJECTED  -> REJECTED
    # =========================================================

    op.execute(
        """
        UPDATE orders
        SET status = 'OPEN'
        WHERE status = 'PENDING'
        """
    )

    op.execute(
        """
        UPDATE orders
        SET status = 'FILLED'
        WHERE status = 'COMPLETED'
        """
    )

    # =========================================================
    # 8. Create executions table
    # =========================================================

    op.create_table(
        "executions",

        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),

        sa.Column(
            "order_id",
            sa.BigInteger(),
            nullable=False,
        ),

        sa.Column(
            "quantity",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "execution_price",
            sa.Numeric(
                precision=14,
                scale=2,
            ),
            nullable=False,
        ),

        sa.Column(
            "executed_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),

        sa.CheckConstraint(
            "quantity > 0",
            name="executions_quantity_check",
        ),

        sa.CheckConstraint(
            "execution_price > 0",
            name="executions_price_check",
        ),

        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint("id"),
    )

    # =========================================================
    # 9. Preserve historical execution data
    # =========================================================

    op.execute(
        """
        INSERT INTO executions (
            order_id,
            quantity,
            execution_price,
            executed_at
        )
        SELECT
            id,
            quantity,
            price_per_share,
            COALESCE(
                executed_at,
                CURRENT_TIMESTAMP
            )
        FROM orders
        WHERE status = 'FILLED'
          AND price_per_share IS NOT NULL
          AND price_per_share > 0
        """
    )

    # =========================================================
    # 10. Populate fill information
    # =========================================================

    op.execute(
        """
        UPDATE orders
        SET
            filled_quantity = quantity,
            average_fill_price = price_per_share
        WHERE status = 'FILLED'
          AND price_per_share IS NOT NULL
          AND price_per_share > 0
        """
    )

    # =========================================================
    # 11. Make side NOT NULL
    # =========================================================

    op.alter_column(
        "orders",
        "side",
        existing_type=sa.VARCHAR(length=4),
        nullable=False,
    )

    # =========================================================
    # 12. Add NEW order constraints
    # =========================================================

    op.create_check_constraint(
        "orders_side_check",
        "orders",
        "side IN ('BUY', 'SELL')",
    )

    op.create_check_constraint(
        "orders_order_type_check",
        "orders",
        """
        order_type IN (
            'MARKET',
            'LIMIT',
            'STOP',
            'STOP_LIMIT'
        )
        """,
    )

    op.create_check_constraint(
        "orders_status_check",
        "orders",
        """
        status IN (
            'NEW',
            'OPEN',
            'PARTIALLY_FILLED',
            'FILLED',
            'CANCELLED',
            'REJECTED'
        )
        """,
    )

    op.create_check_constraint(
        "orders_filled_quantity_check",
        "orders",
        "filled_quantity >= 0",
    )

    op.create_check_constraint(
        "orders_filled_quantity_limit_check",
        "orders",
        "filled_quantity <= quantity",
    )

    op.create_check_constraint(
        "orders_limit_price_check",
        "orders",
        "limit_price IS NULL OR limit_price > 0",
    )

    op.create_check_constraint(
        "orders_stop_price_check",
        "orders",
        "stop_price IS NULL OR stop_price > 0",
    )

    # =========================================================
    # 13. Add idempotency constraint
    # =========================================================

    op.create_unique_constraint(
        "orders_user_client_order_id_key",
        "orders",
        [
            "user_id",
            "client_order_id",
        ],
    )

    # =========================================================
    # 14. Remove old execution-related columns
    # =========================================================

    op.drop_constraint(
        op.f("orders_price_per_share_check"),
        "orders",
        type_="check",
    )

    op.drop_column(
        "orders",
        "total_amount",
    )

    op.drop_column(
        "orders",
        "price_per_share",
    )

    op.drop_column(
        "orders",
        "executed_at",
    )


def downgrade() -> None:
    # =========================================================
    # 1. Restore old columns
    # =========================================================

    op.add_column(
        "orders",
        sa.Column(
            "executed_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )

    op.add_column(
        "orders",
        sa.Column(
            "price_per_share",
            sa.NUMERIC(
                precision=14,
                scale=2,
            ),
            nullable=True,
        ),
    )

    op.add_column(
        "orders",
        sa.Column(
            "total_amount",
            sa.NUMERIC(
                precision=16,
                scale=2,
            ),
            sa.Computed(
                "((quantity)::numeric * price_per_share)",
                persisted=True,
            ),
            nullable=True,
        ),
    )

    # =========================================================
    # 2. Restore execution information
    # =========================================================

    op.execute(
        """
        UPDATE orders o
        SET
            price_per_share = e.execution_price,
            executed_at = e.executed_at
        FROM executions e
        WHERE e.id = (
            SELECT MIN(e2.id)
            FROM executions e2
            WHERE e2.order_id = o.id
        )
        """
    )

    # =========================================================
    # 3. Remove new constraints
    # =========================================================

    op.drop_constraint(
        "orders_stop_price_check",
        "orders",
        type_="check",
    )

    op.drop_constraint(
        "orders_side_check",
        "orders",
        type_="check",
    )

    op.drop_constraint(
        "orders_order_type_check",
        "orders",
        type_="check",
    )

    op.drop_constraint(
        "orders_status_check",
        "orders",
        type_="check",
    )

    op.drop_constraint(
        "orders_limit_price_check",
        "orders",
        type_="check",
    )

    op.drop_constraint(
        "orders_filled_quantity_limit_check",
        "orders",
        type_="check",
    )

    op.drop_constraint(
        "orders_filled_quantity_check",
        "orders",
        type_="check",
    )

    op.drop_constraint(
        "orders_user_client_order_id_key",
        "orders",
        type_="unique",
    )

    # =========================================================
    # 4. Restore old statuses
    # =========================================================

    op.execute(
        """
        UPDATE orders
        SET status = 'COMPLETED'
        WHERE status = 'FILLED'
        """
    )

    op.execute(
        """
        UPDATE orders
        SET status = 'PENDING'
        WHERE status = 'OPEN'
        """
    )

    # =========================================================
    # 5. Remove new side/order-type relationship
    # =========================================================

    op.execute(
        """
        UPDATE orders
        SET order_type = side
        WHERE order_type = 'MARKET'
        """
    )

    # =========================================================
    # 6. Restore old order_type size
    # =========================================================

    op.alter_column(
        "orders",
        "order_type",
        existing_type=sa.String(length=10),
        type_=sa.VARCHAR(length=4),
        existing_nullable=False,
    )

    # =========================================================
    # 7. Remove new columns
    # =========================================================

    op.drop_column(
        "orders",
        "updated_at",
    )

    op.drop_column(
        "orders",
        "client_order_id",
    )

    op.drop_column(
        "orders",
        "average_fill_price",
    )

    op.drop_column(
        "orders",
        "stop_price",
    )

    op.drop_column(
        "orders",
        "limit_price",
    )

    op.drop_column(
        "orders",
        "filled_quantity",
    )

    op.drop_column(
        "orders",
        "side",
    )

    # =========================================================
    # 8. Restore old constraints
    # =========================================================

    op.create_check_constraint(
        op.f("orders_order_type_check"),
        "orders",
        "order_type IN ('BUY', 'SELL')",
    )

    op.create_check_constraint(
        op.f("orders_status_check"),
        "orders",
        """
        status IN (
            'PENDING',
            'COMPLETED',
            'REJECTED'
        )
        """,
    )

    op.create_check_constraint(
        op.f("orders_price_per_share_check"),
        "orders",
        "price_per_share > 0::numeric",
    )

    # =========================================================
    # 9. Remove executions table
    # =========================================================

    op.drop_table("executions")