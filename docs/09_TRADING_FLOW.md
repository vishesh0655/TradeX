# Trading flow

~~~mermaid
flowchart TD
 A[TradingPanel] --> B[POST /orders plus JWT]
 B --> C[Pydantic and domain validation]
 C --> D[OrderService and reservation]
 D --> E[OrderEvaluation / paper execution]
 E --> F[FillProcessor]
 F --> G[AccountingService]
 G --> H[wallet, holding, execution, event, ledger]
 H --> I[commit and response]
 I --> J[App data refresh]
~~~

## BUY

TradingPanel estimates fees, asks for confirmation, then posts the typed order. The backend authenticates, validates values and price-field combinations, finds user/stock/wallet, checks funds including reservation/fee effects, creates the order/reservation, and evaluates eligible paper orders against stored prices. Fills flow through accounting to update cash, holding/cost basis, execution rows, wallet ledger, and events.

## SELL

SELL takes the same path but risk/reservation logic uses available shares, excluding already reserved shares. Accounting reduces the position/cost basis and records realized P&L where applicable, while cash is credited net of fees.

## Rejections/errors

The code handles invalid side/type/quantity/prices, missing/inactive stock, insufficient funds/shares, duplicate IDs/references, order ownership, invalid transitions, and ineligible cancel/modify requests. Browser validation is helpful but the backend remains authoritative.
