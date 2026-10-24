# Order history

GET /orders only returns the authenticated user's orders. It supports limit/offset plus status, symbol, side, order type, and date filtering. The route sets pagination headers.

OrdersPage.jsx renders status, terms, quantity/fill progress, and permitted actions. Selecting a row loads:

- GET /orders/{id}/events: immutable lifecycle audit events.
- GET /orders/{id}/executions: simulated fills with price, fees, and net cash effect.

Cancellation releases remaining reservation. Modification recalculates eligible order reservations. Wallet transaction reference_id connects ledger entries to orders.
