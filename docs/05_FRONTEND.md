# Frontend

The frontend is a React/Vite single-page application. It does not use React Router; App.jsx keeps activePage and conditionally renders pages.

## State and layout

- main.jsx mounts App inside StrictMode.
- App.jsx stores authentication, user, stocks, holdings, portfolio, orders, wallet, transactions, watchlist, selected symbol, loading/errors, and toasts.
- Initial protected loading uses Promise.allSettled for stocks, /me, holdings, portfolio, orders, wallet, wallet transactions, and watchlist.
- TradingShell.jsx supplies desktop/mobile navigation, global stock search, balance/profile/logout chrome.

## UI features

- DashboardPage and MarketsPage show market/account information.
- TradingPanel.jsx supplies BUY/SELL, MARKET/LIMIT/STOP/STOP_LIMIT fields, fee estimation, review, submit and result dialogs.
- OrdersPage shows filters, details, executions, events, cancel/modify controls.
- PortfolioPage shows holdings, available/reserved quantities, valuation and P&L.
- WalletPage shows cash, reservations and ledger.
- WatchlistPage and ProfilePage show saved stocks/account information.

## Authentication UI

Login.jsx uses Firebase email/password then exchanges a verified ID token at /auth/email; it falls back to local legacy /login for old accounts. It initializes Google Identity Services and posts credentials to /auth/google. PhoneLogin components use Firebase phone flow then /auth/phone. Register.jsx is the local registration view.

Remember Me stores the TradeX JWT in localStorage; otherwise it uses sessionStorage. api/client.js clears both on HTTP 401.
