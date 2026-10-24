# Portfolio and P&L

portfolio_valuation.py and trading_queries.py provide the values consumed by PortfolioPage.jsx.

- cash balance: wallet balance.
- reserved cash: wallet reserved_cash.
- available cash: balance minus reserved_cash.
- market value: each holding quantity multiplied by stored current_price, summed.
- portfolio value: cash balance plus market value.
- cost basis: persisted holding cost_basis.
- unrealized P&L: market value minus cost basis.
- realized P&L: sell-fill accounting result.
- total P&L: realized plus unrealized.

PortfolioPage also shows total/reserved/available share quantities. The UI uses en-IN INR formatting. Prices are stored reference values, not live exchange quotes.
