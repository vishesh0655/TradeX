import { DataTable, EmptyState, MetricCard } from '../components/common/ui'
import { formatCurrency, formatPercent, formatQuantity } from '../utils/format'

export default function PortfolioPage({ portfolio, loading, onNavigate, retry, error }) {
  const holdings = portfolio?.holdings || []
  const cashBalance = Number(portfolio?.cash_balance || 0)
  const reservedCash = Number(portfolio?.reserved_cash || 0)
  const availableCash = Number(portfolio?.available_cash ?? (cashBalance - reservedCash))
  const marketValue = Number(portfolio?.market_value || 0)
  const portfolioValue = Number(portfolio?.portfolio_value ?? (cashBalance + marketValue))
  const unrealized = Number(portfolio?.unrealized_pnl || 0)
  const realized = Number(portfolio?.realized_pnl || 0)
  const totalPnl = Number(portfolio?.total_pnl ?? (unrealized + realized))

  return <div className="page-stack">
    <div className="page-title-row"><div><span className="eyebrow">POSITIONS & VALUATION</span><h1>Portfolio</h1><p>Track holdings, valuation, and performance.</p></div></div>
    {error && <div className="page-error" role="alert">{error} <button onClick={retry}>Retry</button></div>}
    <div className="metric-grid metric-grid-three"><MetricCard label="Total portfolio value" value={formatCurrency(portfolioValue)} note="Account balance + holdings"/><MetricCard label="Unrealized P&L" value={`${unrealized > 0 ? '+' : ''}${formatCurrency(unrealized)}`} note="Open positions at reference prices" tone={unrealized >= 0 ? 'positive' : 'negative'}/><MetricCard label="Realized P&L" value={`${realized > 0 ? '+' : ''}${formatCurrency(realized)}`} note="Completed sells" tone={realized >= 0 ? 'positive' : 'negative'}/></div>
    <div className="metric-grid metric-grid-three"><MetricCard label="Holdings market value" value={formatCurrency(marketValue)} note="Reference price × quantity"/><MetricCard label="Available funds" value={formatCurrency(availableCash)} note={`${formatCurrency(reservedCash)} reserved for open orders`}/><MetricCard label="Total P&L" value={`${totalPnl > 0 ? '+' : ''}${formatCurrency(totalPnl)}`} note="Realized + unrealized" tone={totalPnl >= 0 ? 'positive' : 'negative'}/></div>
    <section className="content-card"><div className="section-heading"><div><span className="eyebrow">OPEN POSITIONS</span><h2>Holdings</h2></div><span className="row-count">{holdings.length} instruments</span></div>
      {loading ? <div className="loading-block">Loading portfolio…</div> : holdings.length ? <DataTable><thead><tr><th>Instrument</th><th>Total qty</th><th>Available</th><th>Reserved</th><th>Average cost</th><th>Price</th><th>Market value</th><th>Unrealized P&amp;L</th><th>P&amp;L %</th></tr></thead><tbody>{holdings.map((item) => <tr key={item.stock_symbol}><td><strong>{item.stock_symbol}</strong><span className="table-secondary">{item.company_name}</span></td><td className="numeric">{formatQuantity(item.total_quantity ?? item.quantity)}</td><td className="numeric">{formatQuantity(item.available_quantity ?? item.quantity)}</td><td className="numeric">{formatQuantity(item.reserved_quantity || 0)}</td><td className="numeric">{formatCurrency(item.average_buy_price)}</td><td className="numeric">{formatCurrency(item.current_price)}</td><td className="numeric">{formatCurrency(item.market_value ?? item.current_value)}</td><td className={`numeric ${item.unrealized_pnl >= 0 ? 'positive' : 'negative'}`}>{item.unrealized_pnl > 0 ? '+' : ''}{formatCurrency(item.unrealized_pnl ?? item.profit_loss)}</td><td className={`numeric ${(item.unrealized_pnl_percent ?? item.profit_loss_percent) >= 0 ? 'positive' : 'negative'}`}>{formatPercent(item.unrealized_pnl_percent ?? item.profit_loss_percent)}</td></tr>)}</tbody></DataTable> : <EmptyState title="No holdings yet." detail="Explore markets and place an order to build a position." action={<button className="primary-button" onClick={() => onNavigate('markets')}>Explore markets</button>}/>}
    </section>
    <p className="data-footnote">Prices are stored TradeX reference values, not live exchange quotes. Total portfolio value is account balance plus holdings market value.</p>
  </div>
}
