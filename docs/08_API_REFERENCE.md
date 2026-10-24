# API reference

All endpoints are in backend/app/main.py. JWT means get_current_user requires Authorization: Bearer <TradeX JWT>.

| Method/path | JWT | Behavior |
|---|---:|---|
| GET /, GET /database-check | no | greeting/database diagnostic |
| GET /stocks, GET /stocks/{symbol}/quote | no | active stored prices and quote |
| POST /paper-prices/{symbol} | update token | guarded paper-price update |
| POST /register, POST /login | no | local account/legacy auth |
| POST /auth/email, /auth/phone, /auth/google | no | provider credential exchange |
| GET /me | yes | profile |
| GET /wallet, GET /wallet/transactions | yes | virtual cash and paginated ledger |
| POST /fees/estimate | yes | configured fee estimate |
| GET/POST /watchlist; DELETE /watchlist/{symbol} | yes | saved instruments |
| POST /orders | yes | typed paper order |
| POST /orders/buy, /orders/sell | yes | legacy compatibility routes |
| GET /holdings, GET /portfolio | yes | account positions and valuation |
| GET /orders, GET /orders/{id} | yes | user-scoped order list/detail |
| POST /orders/{id}/cancel; PATCH /orders/{id} | yes | cancel/modify eligible order |
| GET /orders/{id}/executions, /events | yes | paginated fills/audit records |

OrderCreate accepts stock_symbol, side, order_type, quantity, conditional limit_price/stop_price, and optional client_order_id. Query list endpoints support pagination/filtering documented in their route signatures. Expected service failures become 4xx errors; unexpected errors use the generic 500 handler.
