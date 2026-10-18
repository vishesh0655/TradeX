import { useMemo, useState } from 'react'
import { DataTable, EmptyState } from '../components/common/ui'
import TradingPanel from '../components/trading/TradingPanel'
import { formatCurrency } from '../utils/format'

export default function MarketsPage({ stocks, selectedSymbol, setSelectedSymbol, watchlist, onToggleWatchlist, loading, walletBalance, holdings, onPlaceOrder }) {
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState('symbol')
  const selected = stocks.find((stock) => stock.symbol === selectedSymbol)
  const filtered = useMemo(() => stocks
    .filter((stock) => `${stock.symbol} ${stock.company_name}`.toLowerCase().includes(query.toLowerCase()))
    .sort((a, b) => sort === 'price' ? a.current_price - b.current_price : a.symbol.localeCompare(b.symbol)), [stocks, query, sort])

  return <div className="page-stack">
    <div className="page-title-row"><div><span className="eyebrow">SIMULATED INSTRUMENTS</span><h1>Markets</h1><p>Browse the instruments configured in your local paper market.</p></div><span className="market-state"><i/> Simulated quotes</span></div>
    <div className="markets-layout">
      <section className="content-card markets-list-card">
        <div className="market-controls"><label className="search-field"><span className="sr-only">Filter by symbol or company</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter by symbol or company"/></label><label className="sort-field">Sort by <select value={sort} onChange={(event) => setSort(event.target.value)}><option value="symbol">Symbol</option><option value="price">Price</option></select></label></div>
        {loading ? <div className="loading-block">Loading market instruments…</div> : filtered.length ? <DataTable><thead><tr><th>Instrument</th><th>Market</th><th>Simulated price</th><th>Watchlist</th></tr></thead><tbody>{filtered.map((stock) => <tr key={stock.symbol} className={selectedSymbol === stock.symbol ? 'selected-row' : ''} onClick={() => setSelectedSymbol(stock.symbol)}><td><button className="instrument-cell" onClick={() => setSelectedSymbol(stock.symbol)}><strong>{stock.symbol}</strong><span>{stock.company_name}</span></button></td><td><span className="exchange-tag">{stock.exchange || 'PAPER'}</span></td><td className="numeric price-cell">{formatCurrency(stock.current_price)}</td><td><button className={`watch-star${watchlist.some((item) => item.symbol === stock.symbol) ? ' is-watched' : ''}`} onClick={(event) => { event.stopPropagation(); onToggleWatchlist(stock.symbol) }} aria-label={`${watchlist.some((item) => item.symbol === stock.symbol) ? 'Remove from' : 'Add to'} watchlist`}>{watchlist.some((item) => item.symbol === stock.symbol) ? '★' : '☆'}</button></td></tr>)}</tbody></DataTable> : <EmptyState title="No matching instruments" detail="Try another symbol or company name."/>}
        <div className="data-footnote">The backend provides current simulated prices only; daily change, volume, and exchange status are not available.</div>
      </section>
      <aside className="market-detail-column">
        {selected && <section className="content-card stock-detail-card"><span className="eyebrow">INSTRUMENT OVERVIEW</span><div className="stock-detail-title"><div><h2>{selected.symbol}</h2><p>{selected.company_name}</p></div><button className={`watch-star${watchlist.some((item) => item.symbol === selected.symbol) ? ' is-watched' : ''}`} onClick={() => onToggleWatchlist(selected.symbol)} aria-label="Toggle watchlist">{watchlist.some((item) => item.symbol === selected.symbol) ? '★' : '☆'}</button></div><strong className="stock-detail-price">{formatCurrency(selected.current_price)}</strong><span className="stock-data-label">CURRENT SIMULATED PRICE</span><div className="stock-facts"><div><span>Instrument</span><b>{selected.symbol}</b></div><div><span>Market</span><b>Paper market</b></div></div><div className="data-footnote">Day change, historical candles, volume, and other statistics are not available in this dataset.</div></section>}
        <TradingPanel stocks={stocks} selectedSymbol={selectedSymbol} setSelectedSymbol={setSelectedSymbol} walletBalance={walletBalance} holdings={holdings} onPlaceOrder={onPlaceOrder}/>
      </aside>
    </div>
  </div>
}
