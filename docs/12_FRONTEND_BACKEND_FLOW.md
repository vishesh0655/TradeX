# Frontend to backend flow

api/client.js reads VITE_API_URL, sends JSON requests, adds a Bearer token except to anonymous auth calls, and turns failed responses into ApiError. On 401 it clears token stores and dispatches tradex:unauthorized.

## Examples

- Login: Login.jsx obtains a Firebase/Google/legacy credential, api/auth.js calls the corresponding backend route, then the JWT is stored according to Remember Me.
- Buy: TradingPanel.jsx requests POST /fees/estimate, then POST /orders; App.jsx refreshes its account resources after success.
- Sell: same order payload with side SELL; backend verifies available shares.
- Portfolio: App.jsx calls api/portfolio.js:getPortfolio, which calls GET /portfolio; PortfolioPage renders it.

App uses Promise.allSettled for initial account loading. A broken section can surface an error without discarding data from other successful API calls.
