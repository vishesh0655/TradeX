"""persist STOP and STOP_LIMIT trigger state

Revision ID: 20261018_order_stop_triggers
Revises: 20261018_execution_refs
Create Date: 2026-10-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261018_order_stop_triggers"
down_revision: Union[str, Sequence[str], None] = "20261018_execution_refs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("stop_triggered", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "orders",
        sa.Column("triggered_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "orders_stop_trigger_timestamp_check",
        "orders",
        "(stop_triggered = false AND triggered_at IS NULL) OR "
        "(stop_triggered = true AND triggered_at IS NOT NULL)",
    )
    op.create_check_constraint(
        "orders_stop_trigger_type_check",
        "orders",
        "order_type IN ('STOP', 'STOP_LIMIT') OR stop_triggered = false",
    )


def downgrade() -> None:
    op.drop_constraint("orders_stop_trigger_type_check", "orders", type_="check")
    op.drop_constraint("orders_stop_trigger_timestamp_check", "orders", type_="check")
    op.drop_column("orders", "triggered_at")
    op.drop_column("orders", "stop_triggered")
