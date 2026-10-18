import { useEffect, useMemo, useState } from 'react'
import { DataTable, EmptyState } from '../components/common/ui'
import TradingPanel from '../components/trading/TradingPanel'
import { getQuote } from '../api/stocks'
import { formatCurrency, formatDateTime } from '../utils/format'

export default function MarketsPage({ stocks, selectedSymbol, setSelectedSymbol, watchlist, onToggleWatchlist, loading, wallet, holdings, onPlaceOrder }) {
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState('symbol')
  const [quote, setQuote] = useState(null)
  const [quoteError, setQuoteError] = useState(null)
  const [quoteRetry, setQuoteRetry] = useState(0)
  const selected = stocks.find((stock) => stock.symbol === selectedSymbol)
  const filtered = useMemo(() => stocks
    .filter((stock) => `${stock.symbol} ${stock.company_name}`.toLowerCase().includes(query.toLowerCase()))
    .sort((a, b) => sort === 'price' ? a.current_price - b.current_price : a.symbol.localeCompare(b.symbol)), [stocks, query, sort])

  useEffect(() => {
    if (!selectedSymbol) return undefined
    let active = true
    getQuote(selectedSymbol).then((data) => { if (active) setQuote({ ...data, requestSymbol: selectedSymbol }) }).catch((error) => { if (active) setQuoteError({ symbol: selectedSymbol, message: error.message }) })
    return () => { active = false }
  }, [selectedSymbol, quoteRetry])
  const selectedQuote = quote?.requestSymbol === selectedSymbol ? quote : null
  const selectedQuoteError = quoteError?.symbol === selectedSymbol ? quoteError.message : ''

  return <div className="page-stack">
    <div className="page-title-row"><div><span className="eyebrow">MARKETS</span><h1>Markets</h1><p>Browse instruments and place orders.</p></div></div>
    <div className="markets-layout">
      <section className="content-card markets-list-card">
        <div className="market-controls"><label className="search-field"><span className="sr-only">Filter by symbol or company</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter by symbol or company"/></label><label className="sort-field">Sort by <select value={sort} onChange={(event) => setSort(event.target.value)}><option value="symbol">Symbol</option><option value="price">Price</option></select></label></div>
        {loading ? <div className="loading-block">Loading instruments…</div> : filtered.length ? <DataTable><thead><tr><th>Instrument</th><th>Price</th><th>Watchlist</th></tr></thead><tbody>{filtered.map((stock) => <tr key={stock.symbol} className={selectedSymbol === stock.symbol ? 'selected-row' : ''} onClick={() => setSelectedSymbol(stock.symbol)}><td><button className="instrument-cell" onClick={() => setSelectedSymbol(stock.symbol)}><strong>{stock.symbol}</strong><span>{stock.company_name}</span></button></td><td className="numeric price-cell">{formatCurrency(stock.current_price)}</td><td><button className={`watch-star${watchlist.some((item) => item.symbol === stock.symbol) ? ' is-watched' : ''}`} onClick={(event) => { event.stopPropagation(); onToggleWatchlist(stock.symbol) }} aria-label={`${watchlist.some((item) => item.symbol === stock.symbol) ? 'Remove from' : 'Add to'} watchlist`}>{watchlist.some((item) => item.symbol === stock.symbol) ? '★' : '☆'}</button></td></tr>)}</tbody></DataTable> : <EmptyState title="No matching instruments" detail="Try another symbol or company name."/>}
        <div className="data-footnote">Prices shown are stored reference values and may not reflect current exchange prices.</div>
      </section>
      <aside className="market-detail-column">
        {selected && <section className="content-card stock-detail-card"><span className="eyebrow">INSTRUMENT DETAIL</span><div className="stock-detail-title"><div><h2>{selected.symbol}</h2><p>{selected.company_name}</p></div><button className={`watch-star${watchlist.some((item) => item.symbol === selected.symbol) ? ' is-watched' : ''}`} onClick={() => onToggleWatchlist(selected.symbol)} aria-label="Toggle watchlist">{watchlist.some((item) => item.symbol === selected.symbol) ? '★' : '☆'}</button></div><strong className="stock-detail-price">{formatCurrency(selectedQuote?.price ?? selected.current_price)}</strong><span className="stock-data-label">REFERENCE PRICE</span>{selectedQuoteError && <p className="inline-error" role="alert">Quote detail unavailable: {selectedQuoteError} <button className="inline-retry" onClick={() => setQuoteRetry((value) => value + 1)}>Retry</button></p>}<div className="stock-facts"><div><span>Instrument</span><b>{selected.symbol}</b></div><div><span>Price source</span><b>TradeX reference</b></div><div><span>Last updated</span><b>{selectedQuote?.updated_at ? formatDateTime(selectedQuote.updated_at) : 'Not provided'}</b></div></div><div className="data-footnote">This is a stored TradeX price, not a live exchange quote.</div></section>}
        <TradingPanel stocks={stocks} selectedSymbol={selectedSymbol} setSelectedSymbol={setSelectedSymbol} wallet={wallet} holdings={holdings} onPlaceOrder={onPlaceOrder}/>
      </aside>
    </div>
  </div>
}
