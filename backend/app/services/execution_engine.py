from decimal import Decimal

from sqlalchemy.orm import Session

from app import models
from app.services.order_lifecycle import transition_order


class PaperExecutionEngine:
    """Simulated execution venue for TradeX.

    It converts a validated MARKET order into one Execution/fill and applies
    the resulting fill atomically to wallet, holdings, and ledger.
    """

    venue = "PAPER"

    def execute_market(
        self,
        db: Session,
        *,
        order: models.Order,
        stock: models.Stock,
        wallet: models.Wallet,
        holding: models.Holding | None,
    ) -> models.Execution:
        execution_price = Decimal(stock.current_price)
        quantity = order.quantity
        notional = execution_price * quantity

        if order.side == "BUY":
            if wallet.balance < notional:
                raise ValueError("Insufficient balance")

            wallet.balance -= notional

            if holding is None:
                holding = models.Holding(
                    user_id=order.user_id,
                    stock_id=stock.id,
                    quantity=quantity,
                    average_buy_price=execution_price,
                )
                db.add(holding)
            else:
                old_quantity = holding.quantity
                old_value = holding.average_buy_price * old_quantity
                new_quantity = old_quantity + quantity

                holding.quantity = new_quantity
                holding.average_buy_price = (
                    old_value + notional
                ) / new_quantity

            transaction_type = "BUY"
            ledger_amount = -notional

        elif order.side == "SELL":
            if holding is None or holding.quantity < quantity:
                raise ValueError("Insufficient shares to sell")

            wallet.balance += notional

            if holding.quantity == quantity:
                db.delete(holding)
            else:
                holding.quantity -= quantity

            transaction_type = "SELL"
            ledger_amount = notional

        else:
            raise ValueError(f"Unsupported order side: {order.side}")

        execution = models.Execution(
            order_id=order.id,
            quantity=quantity,
            execution_price=execution_price,
        )
        db.add(execution)

        order.filled_quantity = quantity
        order.average_fill_price = execution_price
        transition_order(db, order, "FILLED", event_type="ORDER_FILLED", metadata={
            "filled_quantity": quantity,
            "average_fill_price": str(execution_price),
        })

        db.add(
            models.WalletTransaction(
                wallet_id=wallet.id,
                transaction_type=transaction_type,
                amount=ledger_amount,
                balance_after=wallet.balance,
                reference_id=order.id,
            )
        )

        return execution
