# Learning guide

## Beginner

React renders pages from state. FastAPI turns Python functions into HTTP endpoints. PostgreSQL stores persistent account/trading data. SQLAlchemy maps Python models/queries to SQL. JWT is the signed token used after login.

## Intermediate

Routes authenticate and validate; domain/services own trading rules; models persist effects. Alembic version-controls schema changes. Reservations lower available cash/shares before an order fills.

## Advanced

Trading systems need consistency: an execution, wallet effect, holding update, order status/event, and ledger entry should not only partially succeed. TradeX uses constraints, sessions, unique identifiers, and immutable audit/ledger ideas. Next production concerns include concurrency/locking, idempotency, scheduling, external price/broker adapters, observability, rate limiting, and backup/recovery.
