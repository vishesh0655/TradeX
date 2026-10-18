# TradeX

**Educational Paper Trading Platform**

TradeX is a learning project for practicing stock-order and portfolio workflows.
All funds are virtual and every trade is simulated. Current market prices are
internal stored values used as simulated paper quotes; they are not live
exchange quotes. No real money is involved, no broker or exchange execution
occurs, and TradeX does not provide investment advice. The project is for
educational purposes only.

## Product boundaries

- Virtual wallet balances and simulated fees only.
- Paper order acceptance, evaluation, execution, and settlement only.
- No real-money deposits or withdrawals, payment rails, bank/UPI, Demat, KYC,
  broker integration, or exchange order submission.
- No external market-data feed and no price-generation algorithm in Phase 1.

## Architecture

```text
React / Vite
    │ HTTP + TradeX JWT
    ▼
FastAPI routes ──► domain and services ──► SQLAlchemy ──► PostgreSQL
                         │
                         ├─ Risk and reservations
                         ├─ Order lifecycle and evaluation
                         ├─ Paper execution adapter and fill processor
                         ├─ Accounting, ledger, and valuation
                         └─ MarketPriceProvider (stored-price implementation)
```

Routes authenticate and validate requests, call services, and serialize
responses. Trading decisions and account calculations live in the domain and
service layer. SQLAlchemy transactions group order, reservation, fill, wallet,
holding, ledger, and audit updates. Critical account/order rows are locked to
serialize competing requests.

## Backend structure

The FastAPI application is in `backend/app/main.py`. Shared SQLAlchemy models
and Pydantic API schemas live in `models.py` and `schemas.py`; database setup and
JWT authentication are in `database.py` and `security.py`.

Important services:

- `domain/orders.py`: order type, side, price, quantity, and state rules.
- `services/order_service.py`: order creation, idempotency, cancellation, and
  modification.
- `services/risk_engine.py`: pre-trade checks and cash/share reservation.
- `services/order_lifecycle.py`: allowed state transitions and lifecycle
  events.
- `services/order_evaluation.py`: evaluates supplied prices against open
  LIMIT, STOP, and STOP_LIMIT orders.
- `services/execution_adapter.py` and `execution_engine.py`: execution adapter
  contract and paper implementation.
- `services/fill_processor.py`: atomic fill settlement.
- `services/accounting_service.py` and `fee_engine.py`: virtual cash ledger and
  configurable simulated fees.
- `services/portfolio_valuation.py`: average-cost realized and unrealized P&L.
- `services/trading_queries.py`: user-scoped read models, filters, and
  pagination.
- `services/market_data.py`: current price abstraction and stored-price
  implementation.

## Frontend structure

The React/Vite app is under `frontend/src`. `App.jsx` owns authentication
session state, page-level data loading, and cross-page actions. `api/` contains
the shared HTTP client and endpoint functions. `pages/` contains dashboard,
markets, watchlist, orders, portfolio, wallet, and profile views. The shared
paper order ticket is in `components/trading/TradingPanel.jsx`.

Frontend state is a view of backend data. It does not calculate execution,
reservation, fee, or P&L outcomes as an authority; the backend validates and
settles orders.

## Database structure

PostgreSQL is managed through Alembic. Main entities are:

- `users`, `user_identities`: local and federated identities.
- `wallets`, `wallet_transactions`: virtual cash, reserved cash, and append-only
  ledger activity.
- `stocks`: instrument identity and the current internal stored price.
- `holdings`: total and reserved shares with average cost and cost basis.
- `orders`, `order_reservations`: order terms/lifecycle and remaining reserved
  paper assets.
- `executions`: immutable simulated fills and accounting details.
- `order_events`: append-only lifecycle and audit history.
- `watchlist_items`: user-owned saved instruments.

Database checks enforce important value and state constraints. Unique keys
protect client order IDs and execution references. PostgreSQL triggers prevent
updates/deletes to immutable ledger, execution, and order-event records.

## Order lifecycle

Supported sides are `BUY` and `SELL`; supported types are `MARKET`, `LIMIT`,
`STOP`, and `STOP_LIMIT`. Typical transitions are:

```text
NEW → OPEN → PARTIALLY_FILLED → FILLED
          ├─→ CANCEL_PENDING → CANCELLED
          ├─→ CANCELLED
          ├─→ EXPIRED
          └─→ REJECTED
```

An accepted order is validated and reserved before it can execute. MARKET
orders use the current paper quote immediately. LIMIT orders become eligible
when a supplied price meets the limit. STOP orders trigger once and then
execute under the simplified paper model. STOP_LIMIT orders trigger first and
then wait for their limit condition. This is not exchange order-book matching.

Open or partially filled orders may be cancelled. Eligible unfilled orders may
be modified; changes are risk-checked and reservations are resized in the same
transaction. Idempotency uses a user-scoped `client_order_id`.

## Risk engine and reservations

The risk engine checks active account ownership, tradable instrument, order
terms, buying power, available shares, existing reservations, and duplicate
client IDs. BUY orders reserve virtual cash (including estimated configured
fees); SELL orders reserve shares. Available cash and shares exclude current
reservations. Partial fills shrink the remaining reservation. Cancellation,
rejection, and expiry release the unfilled remainder.

Wallet and holding rows are locked before changing reservations. Order paths
use a consistent account-first lock order so concurrent orders cannot spend or
sell the same paper assets twice.

## Execution architecture

`ExecutionAdapter` returns fill records; the paper adapter is the only active
implementation. `FillProcessor` applies each fill to the order, wallet,
holding, reservation, ledger, and audit events in one transaction. It guards
against duplicate execution references, overfills, invalid prices, and fills
for non-open orders. Multiple fills update weighted average fill price.

## Ledger, fees, and accounting

Balance-affecting activity is recorded as immutable wallet-ledger entries.
Ledger rows include transaction type, signed amount, balance-after, order
reference, and metadata. Reservation activity is recorded for audit and
reconciliation; reservations do not spend cash until a fill settles.

`FeeEngine` reads configurable paper fee rates from environment settings
(`TRADEX_BROKERAGE_BPS`, `TRADEX_PLATFORM_FEE_BPS`, and
`TRADEX_SIMULATED_TAX_BPS`). Rates default to zero. Fees are simulated charges,
not payments to an exchange or service.

Holdings use average-cost accounting. Buy fills add gross cost and simulated
fees to cost basis. Sell fills remove the sold shares' proportional basis and
record realized P&L; remaining shares retain their remaining cost basis.
Unrealized P&L and portfolio value use the current price provider's quote.

## Audit events

Order state changes, reservations, stop triggers, modifications, fills, and
settlement outcomes are represented by immutable `order_events` and execution
records. User-facing order, execution, event, and ledger queries are scoped to
the authenticated owner and support pagination where appropriate.

## API overview

The interactive API schema is available at `/docs` when the FastAPI service is
running. Main endpoint groups include:

- Authentication: `/register`, `/login`, `/auth/email`, `/auth/google`,
  `/auth/phone`, `/me`.
- Paper market: `GET /stocks`, `GET /stocks/{symbol}/quote`.
- Orders: `POST /orders`, `GET /orders`, `GET /orders/{id}`,
  `PATCH /orders/{id}`, `POST /orders/{id}/cancel`, and nested executions and
  events. `POST /orders/buy` and `POST /orders/sell` remain as MARKET-only
  compatibility endpoints; new clients should use `POST /orders`.
- Paper account: `/wallet`, `/wallet/transactions`, `/holdings`, `/portfolio`.
- Watchlist and fee estimate: `/watchlist` and `/fees/estimate`.

All protected account endpoints require a TradeX JWT. Responses describe
simulated paper activity only.

## Local setup

Requirements: Python 3.10+, Node.js/npm, and PostgreSQL. Create a local
`backend/.env` with the required `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`,
`DB_NAME`, and `JWT_SECRET_KEY` values. Configure Google/Firebase credentials
only when using those authentication providers. Do not commit credentials.

Backend (PowerShell):

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Frontend (separate terminal):

```powershell
cd frontend
npm install
npm run dev
```

Set `VITE_API_URL` when the API is not at the frontend's configured local
default. The app uses the existing PostgreSQL database; do not reset it to run
the application.

## Testing and checks

Backend tests use `unittest`:

```powershell
cd backend
python -m unittest discover -s tests -v
```

The PostgreSQL integration journeys run in a temporary isolated schema when
`TRADEX_RUN_POSTGRES_E2E=1`; use a dedicated test database for that run. The
test setup drops only its temporary schema afterward. To run the full suite in
PowerShell, set `$env:TRADEX_RUN_POSTGRES_E2E='1'` before the unittest command.
Frontend checks:

```powershell
cd frontend
npm run lint
npm run build
```

There is currently no frontend unit/component test runner configured.

## Future market simulation (Phase 2)

Phase 1 consumes prices through `MarketPriceProvider`. Its current implementation
reads stored internal instrument prices and does not generate or fetch prices.
Phase 2 can add a `VirtualMarketSimulator` that implements the same provider
contract and emits paper `MarketQuote` values. The order evaluator should
continue to receive quotes; order acceptance, risk rules, execution adapters,
fill processing, accounting, and portfolio calculations should not generate
prices or depend on simulator algorithms. The Phase 2 integration point is the
provider implementation/wiring in `services/market_data.py`, followed by
publishing its quotes to `OrderEvaluationService`.

No external price feed or exchange connection is planned as part of this
educational paper-trading architecture.
