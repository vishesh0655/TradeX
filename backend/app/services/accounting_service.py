"""Append-only paper wallet ledger and execution accounting helpers."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app import models

INITIAL_PAPER_BALANCE = Decimal("1000000.00")


class AccountingService:
    """Write auditable wallet entries for all cash and reservation activity."""

    @staticmethod
    def initialize_wallet(db: Session, *, user_id: int) -> models.Wallet:
        wallet = models.Wallet(
            user_id=user_id,
            balance=INITIAL_PAPER_BALANCE,
            reserved_cash=Decimal("0.00"),
        )
        db.add(wallet)
        db.flush()
        db.add(models.WalletTransaction(
            wallet_id=wallet.id,
            transaction_type="INITIAL_VIRTUAL_BALANCE",
            amount=Decimal(wallet.balance),
            balance_after=Decimal(wallet.balance),
            reference_id=None,
            metadata_json={"account_type": "PAPER"},
        ))
        return wallet

    @staticmethod
    def record_reservation(
        db: Session,
        *,
        wallet: models.Wallet,
        order_id: int,
        event_type: str,
        reserved_cash: Decimal,
        reserved_quantity: int,
    ) -> models.WalletTransaction:
        """Record a zero-cash ledger audit entry for funds/shares encumbered."""
        return AccountingService.record_entry(
            db,
            wallet=wallet,
            transaction_type=event_type,
            amount=Decimal("0.00"),
            reference_id=order_id,
            metadata={
                "reserved_cash": str(reserved_cash),
                "reserved_quantity": reserved_quantity,
            },
        )

    @staticmethod
    def record_entry(
        db: Session,
        *,
        wallet: models.Wallet,
        transaction_type: str,
        amount: Decimal,
        reference_id: int | None,
        metadata: dict | None = None,
        balance_after: Decimal | None = None,
    ) -> models.WalletTransaction:
        entry = models.WalletTransaction(
            wallet_id=wallet.id,
            transaction_type=transaction_type,
            amount=amount,
            balance_after=(
                Decimal(wallet.balance) if balance_after is None else balance_after
            ),
            reference_id=reference_id,
            metadata_json=metadata or {},
        )
        db.add(entry)
        return entry

    @staticmethod
    def record_execution_cash_flow(
        db: Session,
        *,
        wallet: models.Wallet,
        order_id: int,
        side: str,
        gross_notional: Decimal,
        fees,
        balance_before: Decimal,
        balance_after: Decimal,
    ) -> None:
        gross = Decimal(gross_notional)
        fees_total = Decimal(fees.total)
        execution_amount = -gross if side == "BUY" else gross
        intermediate_balance = Decimal(balance_before) + execution_amount
        AccountingService.record_entry(
            db,
            wallet=wallet,
            transaction_type=f"{side}_EXECUTION",
            amount=execution_amount,
            balance_after=intermediate_balance,
            reference_id=order_id,
            metadata={"gross_notional": str(gross)},
        )
        if fees_total:
            AccountingService.record_entry(
                db,
                wallet=wallet,
                transaction_type="TRADING_FEE",
                amount=-fees_total,
                balance_after=Decimal(balance_after),
                reference_id=order_id,
                metadata={
                    "brokerage": str(fees.brokerage),
                    "platform": str(fees.platform),
                    "taxes": str(fees.taxes),
                    "side": side,
                },
            )


accounting_service = AccountingService()
