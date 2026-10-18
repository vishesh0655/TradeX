"""make order audit events immutable in PostgreSQL

Revision ID: 20261018_order_events_immutable
Revises: 20261018_paper_accounting
Create Date: 2026-10-18
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20261018_order_events_immutable"
down_revision: Union[str, Sequence[str], None] = "20261018_paper_accounting"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION reject_order_event_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Order audit events are immutable';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER order_events_immutable
        BEFORE UPDATE OR DELETE ON order_events
        FOR EACH ROW EXECUTE FUNCTION reject_order_event_mutation()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS order_events_immutable ON order_events")
    op.execute("DROP FUNCTION IF EXISTS reject_order_event_mutation()")
