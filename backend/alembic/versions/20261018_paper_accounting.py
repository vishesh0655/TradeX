"""add paper execution accounting, ledger metadata and immutability

Revision ID: 20261018_paper_accounting
Revises: 20261018_order_stop_triggers
Create Date: 2026-10-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20261018_paper_accounting"
down_revision: Union[str, Sequence[str], None] = "20261018_order_stop_triggers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "wallet_transactions",
        sa.Column("metadata_json", postgresql.JSONB(),
                  server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.add_column(
        "holdings",
        sa.Column("cost_basis", sa.Numeric(14, 2), server_default=sa.text("0.00"), nullable=False),
    )
    op.execute(
        "UPDATE holdings SET cost_basis = average_buy_price * quantity"
    )
    op.create_check_constraint("holdings_cost_basis_check", "holdings", "cost_basis >= 0")

    for column in ("gross_notional", "fees", "net_cash_effect", "cost_basis", "realized_pnl"):
        op.add_column(
            "executions",
            # Historical execution rows are immutable, so new accounting
            # columns stay NULL until populated for a newly processed fill.
            sa.Column(column, sa.Numeric(14, 2), nullable=True),
        )
    op.create_check_constraint(
        "executions_gross_notional_check", "executions", "gross_notional >= 0"
    )
    op.create_check_constraint("executions_fees_check", "executions", "fees >= 0")
    op.create_check_constraint("executions_cost_basis_check", "executions", "cost_basis >= 0")

    # Reconstruct a virtual opening balance so the signed ledger reconciles to
    # the current wallet, including accounts created before ledger funding entries.
    op.execute(
        """
        INSERT INTO wallet_transactions
            (wallet_id, transaction_type, amount, balance_after, reference_id,
             metadata_json, created_at)
        SELECT w.id, 'INITIAL_VIRTUAL_BALANCE',
               w.balance - COALESCE(SUM(t.amount), 0),
               w.balance - COALESCE(SUM(t.amount), 0),
               NULL, jsonb_build_object(
                   'account_type', 'PAPER', 'migration_backfill', true
               ),
               w.created_at
        FROM wallets AS w
        LEFT JOIN wallet_transactions AS t ON t.wallet_id = w.id
        WHERE NOT EXISTS (
            SELECT 1 FROM wallet_transactions AS initial
            WHERE initial.wallet_id = w.id
              AND initial.transaction_type = 'INITIAL_VIRTUAL_BALANCE'
        )
        GROUP BY w.id, w.balance, w.created_at
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_wallet_transaction_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'wallet ledger entries are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER wallet_transactions_immutable
        BEFORE UPDATE OR DELETE ON wallet_transactions
        FOR EACH ROW EXECUTE FUNCTION reject_wallet_transaction_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS wallet_transactions_immutable ON wallet_transactions")
    op.execute("DROP FUNCTION IF EXISTS reject_wallet_transaction_mutation()")
    op.execute(
        """
        DELETE FROM wallet_transactions
        WHERE transaction_type = 'INITIAL_VIRTUAL_BALANCE'
          AND metadata_json->>'migration_backfill' = 'true'
        """
    )
    op.drop_constraint("executions_gross_notional_check", "executions", type_="check")
    op.drop_constraint("executions_fees_check", "executions", type_="check")
    op.drop_constraint("executions_cost_basis_check", "executions", type_="check")
    for column in reversed(("gross_notional", "fees", "net_cash_effect", "cost_basis", "realized_pnl")):
        op.drop_column("executions", column)
    op.drop_constraint("holdings_cost_basis_check", "holdings", type_="check")
    op.drop_column("holdings", "cost_basis")
    op.drop_column("wallet_transactions", "metadata_json")
