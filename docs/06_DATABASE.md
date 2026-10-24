# Database

The ORM source is backend/app/models.py. Alembic revisions under backend/alembic/versions evolve the database.

~~~mermaid
erDiagram
  USERS ||--|| WALLETS : owns
  USERS ||--o{ ORDERS : places
  USERS ||--o{ HOLDINGS : owns
  USERS ||--o{ USER_IDENTITIES : has
  USERS ||--o{ WATCHLIST_ITEMS : saves
  STOCKS ||--o{ ORDERS : traded_in
  STOCKS ||--o{ HOLDINGS : held_as
  ORDERS ||--o{ EXECUTIONS : receives
  ORDERS ||--o{ ORDER_EVENTS : records
  ORDERS ||--|| ORDER_RESERVATIONS : reserves
  WALLETS ||--o{ WALLET_TRANSACTIONS : records
~~~

| Table | Purpose and important constraints |
|---|---|
| users | account fields; unique email |
| user_identities | provider/provider_subject unique pair; cascades with user |
| wallets | one wallet per user; balance and reserved_cash checks |
| wallet_transactions | wallet ledger with order reference/JSON metadata; mutation rejected by model listener |
| stocks | unique symbol, company, exchange, stored current_price, active flag |
| orders | side/type/status, quantities, limit/stop fields, client id; checks enforce valid term combinations |
| order_events | append-only audit events; indexed order_id |
| executions | fills with unique execution_ref and accounting columns |
| holdings | one user/stock position, quantities, reservation, average price, cost basis |
| order_reservations | one order reservation; state ACTIVE/RELEASED/SETTLED |
| watchlist_items | one saved stock per user/stock pair |

Derived Python properties are Order.remaining_quantity, Wallet.available_cash, and Holding.available_quantity. They are not separate columns.
