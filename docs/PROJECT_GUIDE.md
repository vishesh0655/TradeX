# TradeX technical guide

TradeX is a paper-trading web app: it manages virtual funds, stored stock reference prices, watchlists, orders, fills, portfolio valuation, P&L, and audit records. It does not connect to a broker or an exchange.

## Architecture

~~~text
User
  ↓
React/Vite frontend
  ↓ fetch() plus Bearer JWT
FastAPI API
  ↓ authentication, validation, services
SQLAlchemy
  ↓
PostgreSQL
  ↓ JSON response
React state and UI
~~~

The React state coordinator is frontend/src/App.jsx. The API entry point is backend/app/main.py. The database session dependency is backend/app/database.py:get_db.

## Technologies

- React 19 + Vite, Fetch API, Firebase client SDK.
- FastAPI, Pydantic, SQLAlchemy, psycopg, passlib/bcrypt, python-jose, Google auth.
- PostgreSQL plus Alembic migrations.
- Python unittest tests.

## Read next

- [Overview](01_PROJECT_OVERVIEW.md)
- [Architecture](02_ARCHITECTURE.md)
- [Structure](03_PROJECT_STRUCTURE.md)
- [Backend](04_BACKEND.md)
- [Frontend](05_FRONTEND.md)
- [Database](06_DATABASE.md)
- [Authentication](07_AUTHENTICATION.md)
- [API reference](08_API_REFERENCE.md)
- [Trading flow](09_TRADING_FLOW.md)
- [Portfolio and P&L](10_PORTFOLIO_AND_PNL.md)
- [Order history](11_ORDER_HISTORY.md)
- [Frontend/backend flow](12_FRONTEND_BACKEND_FLOW.md)
- [Alembic](13_ALEMBIC_AND_MIGRATIONS.md)
- [Testing](14_TESTING.md)
- [Configuration](15_CONFIGURATION.md)
- [Local setup](16_LOCAL_SETUP.md)
- [Error handling](17_ERROR_HANDLING.md)
- [Limitations](18_CURRENT_LIMITATIONS.md)
- [Learning guide](19_LEARNING_GUIDE.md)

## Complete TradeX request lifecycle

### Dashboard

~~~text
User opens dashboard
  ↓
App.jsx sees a JWT and requests stocks, profile, holdings, portfolio,
orders, wallet, ledger, and watchlist concurrently
  ↓
api/client.js adds Authorization: Bearer <token>
  ↓
FastAPI verifies the JWT and identifies the user
  ↓
SQLAlchemy queries PostgreSQL
  ↓
JSON returns to App.jsx
  ↓
React pages render successful sections and show individual failures
~~~

### BUY

~~~text
User clicks BUY in TradingPanel
  ↓
React validates basic inputs and estimates fees
  ↓
POST /orders with JWT
  ↓
FastAPI validates terms and authenticates user
  ↓
OrderService checks funds, stock, and order state; reserves assets
  ↓
evaluation/execution/accounting services process eligible paper fills
  ↓
wallet, holding, order, execution, ledger, and event effects commit together
  ↓
React refreshes account data
~~~
