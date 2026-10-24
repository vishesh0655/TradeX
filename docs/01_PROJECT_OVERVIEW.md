# Project overview

TradeX is a virtual/paper trading application using INR-formatted UI values and stored stock reference prices.

## Implemented

- Local registration and legacy email/password login.
- Firebase verified-email and phone credential exchange; Google credential login.
- JWT-protected account and trading endpoints.
- Stocks/quotes, watchlist, wallet ledger, holdings, portfolio, order history, executions, events, cancellation, modification, and fee estimates.
- MARKET, LIMIT, STOP, and STOP_LIMIT paper order terms.
- Cash/share reservations and paper accounting.

## Boundary

No real-money transfers, brokerage account, live exchange connection, or real exchange execution is evidenced. Stored prices come from the database.

## Important locations

- Backend: backend/app/
- Migrations: backend/alembic/
- Tests: backend/tests/
- Frontend: frontend/src/

Firebase/Google provider console configuration cannot be confirmed from source without inspecting external services or secrets.
