"""enforce order price fields by order type

Revision ID: 20261018_order_domain
Revises: 20261018_watchlist
Create Date: 2026-10-18
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20261018_order_domain"
down_revision: Union[str, Sequence[str], None] = "20261018_watchlist"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PRICE_FIELDS_CHECK = (
    "(order_type = 'MARKET' AND limit_price IS NULL AND stop_price IS NULL) OR "
    "(order_type = 'LIMIT' AND limit_price IS NOT NULL AND limit_price > 0 AND stop_price IS NULL) OR "
    "(order_type = 'STOP' AND limit_price IS NULL AND stop_price IS NOT NULL AND stop_price > 0) OR "
    "(order_type = 'STOP_LIMIT' AND limit_price IS NOT NULL AND limit_price > 0 "
    "AND stop_price IS NOT NULL AND stop_price > 0)"
)


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM orders WHERE NOT ("
        + PRICE_FIELDS_CHECK
        + ")) THEN "
        "RAISE EXCEPTION 'Cannot enforce order price rules: existing orders have "
        "price fields inconsistent with their order type. Correct those rows "
        "before retrying this migration.'; "
        "END IF; END $$"
    )

    op.create_check_constraint(
        "orders_price_fields_by_type_check",
        "orders",
        PRICE_FIELDS_CHECK,
    )


def downgrade() -> None:
    op.drop_constraint(
        "orders_price_fields_by_type_check",
        "orders",
        type_="check",
    )
