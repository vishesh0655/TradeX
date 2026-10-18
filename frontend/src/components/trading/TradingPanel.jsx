import { useMemo, useState } from 'react'
import { formatCurrency } from '../../utils/format'
import { Modal } from '../common/ui'

export default function TradingPanel({ stocks, selectedSymbol, setSelectedSymbol, walletBalance, holdings, onPlaceOrder }) {
  const [side, setSide] = useState('BUY')
  const [orderType, setOrderType] = useState('MARKET')
  const [quantity, setQuantity] = useState('1')
  const [limitPrice, setLimitPrice] = useState('')
  const [review, setReview] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const stock = stocks.find((item) => item.symbol === selectedSymbol)
  const holding = holdings.find((item) => item.stock_symbol === selectedSymbol)
  const qty = Number(quantity)
  const price = orderType === 'LIMIT' ? Number(limitPrice) : Number(stock?.current_price || 0)
  const estimatedValue = useMemo(() => qty > 0 && price > 0 ? qty * price : 0, [qty, price])

  const submit = async () => {
    setSubmitting(true); setError('')
    try {
      const order = await onPlaceOrder({
        stock_symbol: selectedSymbol,
        side,
        order_type: orderType,
        quantity: qty,
        ...(orderType === 'LIMIT' ? { limit_price: Number(limitPrice) } : {}),
      })
      setReview(false)
      setQuantity('1')
      setLimitPrice('')
      return order
    } catch (failure) {
      setError(failure.message)
    } finally { setSubmitting(false) }
  }

  return <section className="trade-panel">
    <div className="panel-heading"><div><span className="eyebrow">PAPER EXECUTION</span><h2>Place an order</h2></div><span className="exchange-tag">SIMULATED</span></div>
    <label className="field-label" htmlFor="trade-symbol">Instrument</label>
    <select id="trade-symbol" value={selectedSymbol} onChange={(event) => setSelectedSymbol(event.target.value)}>{stocks.map((item) => <option key={item.symbol} value={item.symbol}>{item.symbol} · {item.company_name}</option>)}</select>
    {stock && <div className="trade-quote"><div><strong>{stock.symbol}</strong><span>{stock.company_name}</span></div><b>{formatCurrency(stock.current_price)}</b></div>}
    <div className="side-toggle" role="group" aria-label="Order side"><button className={side === 'BUY' ? 'selected buy-selected' : ''} onClick={() => setSide('BUY')}>Buy</button><button className={side === 'SELL' ? 'selected sell-selected' : ''} onClick={() => setSide('SELL')}>Sell</button></div>
    <label className="field-label" htmlFor="order-type">Order type</label><select id="order-type" value={orderType} onChange={(event) => setOrderType(event.target.value)}><option value="MARKET">Market</option><option value="LIMIT">Limit</option></select>
    <div className="field-grid"><div><label className="field-label" htmlFor="quantity">Quantity</label><input id="quantity" type="number" min="1" step="1" value={quantity} onChange={(event) => setQuantity(event.target.value)} /></div>{orderType === 'LIMIT' && <div><label className="field-label" htmlFor="limit-price">Limit price</label><input id="limit-price" type="number" min="0.01" step="0.01" placeholder="0.00" value={limitPrice} onChange={(event) => setLimitPrice(event.target.value)} /></div>}</div>
    <div className="trade-context"><span>Virtual cash balance</span><strong>{formatCurrency(walletBalance)}</strong><span>Owned shares</span><strong>{holding?.quantity || 0}</strong><span>Estimated order value</span><strong>{formatCurrency(estimatedValue)}</strong></div>
    <p className="fee-note">No simulated fee schedule is configured yet.</p>
    {orderType === 'LIMIT' && <p className="order-capability-note">Limit orders remain open. Resource reservation and automatic matching are not yet implemented.</p>}
    <button className={`primary-button trade-submit ${side === 'SELL' ? 'button-sell' : ''}`} disabled={!stock || !Number.isInteger(qty) || qty < 1 || (orderType === 'LIMIT' && (!Number.isFinite(Number(limitPrice)) || Number(limitPrice) <= 0))} onClick={() => { setError(''); setReview(true) }}>Review {side.toLowerCase()} order</button>
    {error && <p className="inline-error" role="alert">{error}</p>}
    <p className="simulated-disclaimer">Orders are matched by the TradeX paper simulator. No real money or exchange is involved.</p>
    {review && <Modal title="Review order" eyebrow="VIRTUAL FUNDS ONLY" onClose={() => !submitting && setReview(false)}>
      <div className="review-instrument"><div><strong>{stock?.symbol}</strong><span>{stock?.company_name}</span></div><b>{formatCurrency(stock?.current_price)}</b></div>
      <div className="review-side"><span className={side === 'BUY' ? 'positive' : 'negative'}>{side}</span><span>{orderType} · {qty} {qty === 1 ? 'share' : 'shares'}</span></div>
      {orderType === 'LIMIT' && <div className="review-row"><span>Limit price</span><strong>{formatCurrency(Number(limitPrice))}</strong></div>}
      <div className="review-row"><span>Estimated value</span><strong>{formatCurrency(estimatedValue)}</strong></div>
      <div className="review-row"><span>Charges</span><strong>Not configured</strong></div>
      <div className="review-row"><span>Virtual cash balance</span><strong>{formatCurrency(walletBalance)}</strong></div>
      <div className="paper-review-banner">PAPER ORDER <span>VIRTUAL FUNDS · SIMULATED EXECUTION</span></div>
      <div className="modal-actions"><button className="secondary-button" disabled={submitting} onClick={() => setReview(false)}>Back</button><button className={`primary-button ${side === 'SELL' ? 'button-sell' : ''}`} disabled={submitting} onClick={submit}>{submitting ? 'Submitting…' : 'Place paper order'}</button></div>
      {error && <p className="inline-error" role="alert">{error}</p>}
    </Modal>}
  </section>
}
