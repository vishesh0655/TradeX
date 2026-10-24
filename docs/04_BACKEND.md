# Backend

backend/app/main.py creates the FastAPI application and defines all routes. It has a generic exception handler that logs unexpected exceptions and returns HTTP 500 without internal details.

## Supporting modules

- security.py: bcrypt/passlib password helpers, JWT helpers, OAuth2 Bearer extraction, get_current_user.
- schemas.py: request validation and response shapes.
- models.py: ORM tables, relationships, constraints, and immutable-event listeners.
- domain/orders.py: enums and shared term/fill validation.
- services/: reusable business logic.

| Service | Actual responsibility |
|---|---|
| order_service.py | creation, modification, cancellation, reservation |
| order_evaluation.py | checks open orders against stored price |
| execution_engine.py / execution_adapter.py | paper execution abstraction |
| fill_processor.py | validates, deduplicates, records fills |
| accounting_service.py | wallet, holding, cost basis, realized P&L, ledger |
| risk_engine.py | available funds/shares validation |
| fee_engine.py | fee estimates |
| portfolio_valuation.py | portfolio aggregates |
| trading_queries.py | user-scoped pages/details |
| market_data.py | stored-price provider |
| paper_price_update.py | guarded paper-price update |
| order_lifecycle.py | status transitions and events |

Routes use Depends(get_db); protected routes also use Depends(get_current_user).
