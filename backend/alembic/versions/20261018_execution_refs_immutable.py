"""add unique execution references and database immutability

Revision ID: 20261018_execution_refs
Revises: 20261018_order_reservations
Create Date: 2026-10-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261018_execution_refs"
down_revision: Union[str, Sequence[str], None] = "20261018_order_reservations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("executions", sa.Column("execution_ref", sa.String(100), nullable=True))
    op.execute("UPDATE executions SET execution_ref = 'LEGACY-' || id::text WHERE execution_ref IS NULL")
    op.alter_column("executions", "execution_ref", nullable=False)
    op.create_unique_constraint(
        "executions_execution_ref_key", "executions", ["execution_ref"]
    )
    op.execute(sa.text("""
        CREATE FUNCTION reject_execution_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Execution records are immutable';
        END;
        $$
    """))
    op.execute(sa.text("""
        CREATE TRIGGER executions_immutable
        BEFORE UPDATE OR DELETE ON executions
        FOR EACH ROW EXECUTE FUNCTION reject_execution_mutation()
    """))


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS executions_immutable ON executions")
    op.execute("DROP FUNCTION IF EXISTS reject_execution_mutation()")
    op.drop_constraint("executions_execution_ref_key", "executions", type_="unique")
    op.drop_column("executions", "execution_ref")
