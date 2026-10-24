# Current limitations

## Implemented

- Internal virtual funds and stored stock reference prices.
- Paper orders, fills, reservations, ledger, P&L views, and React UI.
- Local/provider authentication flows.

## Not established as implemented/production ready

- Real-money deposits, withdrawals, brokerage accounts, or exchange execution.
- Live market-feed integration; current prices come from PostgreSQL.
- A demonstrated background scheduler continually evaluating open stop/limit orders. Evaluation services exist, but scheduling/deployment orchestration was not found.
- Rate limiting, background queue workers, monitoring, deployment configuration, or database backup process.
- Native Android/iOS clients.

Provider setup, CORS/deployment policy, current migration state, and production secrets require environment-specific verification.
