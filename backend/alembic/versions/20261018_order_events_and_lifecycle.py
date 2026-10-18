"""add order lifecycle audit events and terminal statuses

Revision ID: 20261018_order_events
Revises: 48037e0cb146
Create Date: 2026-10-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20261018_order_events"
down_revision: Union[str, Sequence[str], None] = "48037e0cb146"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("orders_status_check", "orders", type_="check")
    op.create_check_constraint(
        "orders_status_check",
        "orders",
        "status IN ('NEW', 'OPEN', 'PARTIALLY_FILLED', 'FILLED', "
        "'CANCEL_PENDING', 'CANCELLED', 'REJECTED', 'EXPIRED')",
    )
    op.create_table(
        "order_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "order_id",
            sa.BigInteger(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_order_events_order_id", "order_events", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_order_events_order_id", table_name="order_events")
    op.drop_table("order_events")
    op.drop_constraint("orders_status_check", "orders", type_="check")
    op.create_check_constraint(
        "orders_status_check",
        "orders",
        "status IN ('NEW', 'OPEN', 'PARTIALLY_FILLED', 'FILLED', 'CANCELLED', 'REJECTED')",
    )
