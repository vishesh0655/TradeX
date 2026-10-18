import { useEffect, useMemo, useState } from 'react'
import { estimateOrderFees } from '../../api/fees'
import { formatCurrency, formatDateTime, formatQuantity } from '../../utils/format'
import { Modal, StatusBadge } from '../common/ui'

const orderTypeNames = {
  MARKET: 'Market',
  LIMIT: 'Limit',
  STOP: 'Stop',
  STOP_LIMIT: 'Stop-limit',
}

export default function TradingPanel({
  stocks,
  selectedSymbol,
  setSelectedSymbol,
  wallet,
  holdings,
  onPlaceOrder,
}) {
  const [side, setSide] = useState('BUY')
  const [orderType, setOrderType] = useState('MARKET')
  const [quantity, setQuantity] = useState('1')
  const [limitPrice, setLimitPrice] = useState('')
  const [stopPrice, setStopPrice] = useState('')
  const [reviewOpen, setReviewOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [feeEstimate, setFeeEstimate] = useState(null)
  const [feeLoading, setFeeLoading] = useState(false)
  const [feeError, setFeeError] = useState('')
  const [feeRetry, setFeeRetry] = useState(0)
  const [result, setResult] = useState(null)

  const stock = stocks.find((item) => item.symbol === selectedSymbol)
  const holding = holdings.find((item) => item.stock_symbol === selectedSymbol)
  const parsedQuantity = Number(quantity)
  const priceText = orderType === 'LIMIT' || orderType === 'STOP_LIMIT'
    ? limitPrice
    : orderType === 'STOP' ? stopPrice : stock?.current_price
  const estimatePrice = Number(priceText)
  const estimatedValue = useMemo(() => (
    Number.isInteger(parsedQuantity) && parsedQuantity > 0 && Number.isFinite(estimatePrice)
      ? parsedQuantity * estimatePrice
      : 0
  ), [parsedQuantity, estimatePrice])
  const availableCash = Number(wallet?.available_cash ?? wallet?.balance ?? 0)
  const reservedCash = Number(wallet?.reserved_cash ?? 0)
  const availableShares = Number(holding?.available_quantity ?? holding?.quantity ?? 0)
  const reservedShares = Number(holding?.reserved_quantity ?? 0)
  const insufficientShares = side === 'SELL' && parsedQuantity > availableShares
  const pricesValid = (orderType === 'MARKET')
    || (orderType === 'LIMIT' && Number(limitPrice) > 0)
    || (orderType === 'STOP' && Number(stopPrice) > 0)
    || (orderType === 'STOP_LIMIT' && Number(limitPrice) > 0 && Number(stopPrice) > 0)
  const formValid = Boolean(stock)
    && Number.isInteger(parsedQuantity)
    && parsedQuantity > 0
    && pricesValid

  useEffect(() => {
    if (!formValid || estimatedValue <= 0) return undefined
    let active = true
    const timer = setTimeout(async () => {
      setFeeLoading(true)
      setFeeError('')
      try {
        const estimate = await estimateOrderFees({ side, gross_notional: estimatedValue })
        if (active) setFeeEstimate(estimate)
      } catch (requestError) {
        if (active) {
          setFeeEstimate(null)
          setFeeError({ side, gross_notional: estimatedValue, message: requestError.message })
        }
      } finally {
        if (active) setFeeLoading(false)
      }
    }, 250)
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [side, estimatedValue, formValid, feeRetry])

  const visibleFeeEstimate = formValid && estimatedValue > 0
    && feeEstimate?.side === side && Number(feeEstimate?.gross_notional) === estimatedValue
    ? feeEstimate
    : null
  const visibleFeeError = formValid && estimatedValue > 0
    && feeError?.side === side && Number(feeError?.gross_notional) === estimatedValue
    ? feeError.message
    : ''
  const estimatedFee = Number(visibleFeeEstimate?.total_fees ?? 0)
  const estimatedBuySpend = estimatedValue + estimatedFee
  const insufficientFunds = side === 'BUY' && estimatedValue > 0 && estimatedBuySpend > availableCash

  const resetOrder = () => {
    setReviewOpen(false)
    setResult(null)
    setQuantity('1')
    setLimitPrice('')
    setStopPrice('')
  }

  const submitOrder = async () => {
    setSubmitting(true)
    setError('')
    try {
      const payload = {
        stock_symbol: selectedSymbol,
        side,
        order_type: orderType,
        quantity: parsedQuantity,
        ...(orderType === 'LIMIT' || orderType === 'STOP_LIMIT'
          ? { limit_price: Number(limitPrice) }
          : {}),
        ...(orderType === 'STOP' || orderType === 'STOP_LIMIT'
          ? { stop_price: Number(stopPrice) }
          : {}),
      }
      const submitted = await onPlaceOrder(payload)
      setReviewOpen(false)
      setResult({ ...submitted, estimated_fees: visibleFeeEstimate?.total_fees ?? null })
      setQuantity('1')
      setLimitPrice('')
      setStopPrice('')
    } catch (requestError) {
      setError(requestError.message || 'Order could not be submitted. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return <section className="trade-panel">
    <div className="panel-heading">
      <div><span className="eyebrow">ORDER TICKET</span><h2>Place an order</h2></div>
    </div>
    <label className="field-label" htmlFor="trade-symbol">Instrument</label>
    <select id="trade-symbol" value={selectedSymbol} onChange={(event) => setSelectedSymbol(event.target.value)}>
      {stocks.map((item) => <option key={item.symbol} value={item.symbol}>{item.symbol} · {item.company_name}</option>)}
    </select>
    {stock && <div className="trade-quote"><div><strong>{stock.symbol}</strong><span>{stock.company_name}</span><small>Reference price</small></div><b>{formatCurrency(stock.current_price)}</b></div>}

    <div className="side-toggle" role="group" aria-label="Order side">
      <button type="button" className={side === 'BUY' ? 'selected buy-selected' : ''} onClick={() => setSide('BUY')}>Buy</button>
      <button type="button" className={side === 'SELL' ? 'selected sell-selected' : ''} onClick={() => setSide('SELL')}>Sell</button>
    </div>
    <label className="field-label" htmlFor="order-type">Order type</label>
    <select id="order-type" value={orderType} onChange={(event) => setOrderType(event.target.value)}>
      {Object.entries(orderTypeNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
    </select>
    <div className="field-grid">
      <div><label className="field-label" htmlFor="quantity">Quantity</label><input id="quantity" type="number" min="1" step="1" value={quantity} onChange={(event) => setQuantity(event.target.value)} /></div>
      {(orderType === 'LIMIT' || orderType === 'STOP_LIMIT') && <div><label className="field-label" htmlFor="limit-price">Limit price</label><input id="limit-price" type="number" min="0.01" step="0.01" placeholder="0.00" value={limitPrice} onChange={(event) => setLimitPrice(event.target.value)} /></div>}
      {(orderType === 'STOP' || orderType === 'STOP_LIMIT') && <div><label className="field-label" htmlFor="stop-price">Stop price</label><input id="stop-price" type="number" min="0.01" step="0.01" placeholder="0.00" value={stopPrice} onChange={(event) => setStopPrice(event.target.value)} /></div>}
    </div>

    <div className="trade-context">
      <span>Available funds</span><strong>{formatCurrency(availableCash)}</strong>
      <span>Reserved cash</span><strong>{formatCurrency(reservedCash)}</strong>
      <span>Available shares</span><strong>{formatQuantity(availableShares)}</strong>
      <span>Reserved shares</span><strong>{formatQuantity(reservedShares)}</strong>
      <span>Estimated order value</span><strong>{formatCurrency(estimatedValue)}</strong>
      <span>Estimated fees</span><strong>{formValid && feeLoading ? 'Estimating…' : visibleFeeEstimate ? formatCurrency(visibleFeeEstimate.total_fees) : 'Unavailable'}</strong>
    </div>
    <p className="fee-note">Fees are estimated from TradeX's configured schedule.</p>
    {visibleFeeError && <p className="inline-error" role="alert">Fee estimate unavailable: {visibleFeeError}. TradeX will validate the order before acceptance. <button className="inline-retry" onClick={() => setFeeRetry((value) => value + 1)}>Retry</button></p>}
    {insufficientFunds && <p className="order-capability-note" role="status">Estimated purchase cost exceeds available funds. Reduce quantity or price.</p>}
    {insufficientShares && <p className="order-capability-note" role="status">You have fewer available shares than this sell quantity.</p>}
    <button className={`primary-button trade-submit ${side === 'SELL' ? 'button-sell' : ''}`} disabled={!formValid || insufficientFunds || insufficientShares} onClick={() => { setError(''); setResult(null); setReviewOpen(true) }}>
      Review {side.toLowerCase()} order
    </button>
    {error && <p className="inline-error" role="alert">{error}</p>}
    {reviewOpen && <Modal title="Review order" eyebrow="ORDER CONFIRMATION" onClose={() => !submitting && setReviewOpen(false)}>
      <div className="review-instrument"><div><strong>{stock?.symbol}</strong><span>{stock?.company_name} · Reference price</span></div><b>{formatCurrency(stock?.current_price)}</b></div>
      <div className="review-side"><span className={side === 'BUY' ? 'positive' : 'negative'}>{side}</span><span>{orderTypeNames[orderType]} · {formatQuantity(parsedQuantity)} shares</span></div>
      {(orderType === 'LIMIT' || orderType === 'STOP_LIMIT') && <div className="review-row"><span>Limit price</span><strong>{formatCurrency(Number(limitPrice))}</strong></div>}
      {(orderType === 'STOP' || orderType === 'STOP_LIMIT') && <div className="review-row"><span>Stop price</span><strong>{formatCurrency(Number(stopPrice))}</strong></div>}
      <div className="review-row"><span>Estimated order value</span><strong>{formatCurrency(estimatedValue)}</strong></div>
      <div className="review-row"><span>Estimated fees</span><strong>{visibleFeeEstimate ? formatCurrency(visibleFeeEstimate.total_fees) : 'Not available'}</strong></div>
      <div className="review-row"><span>{side === 'BUY' ? 'Available funds' : 'Available shares'}</span><strong>{side === 'BUY' ? formatCurrency(availableCash) : formatQuantity(availableShares)}</strong></div>
      <p className="account-execution-note">TradeX uses account funds and stored reference prices. Orders are not sent to a broker or exchange.</p>
      <div className="modal-actions"><button className="secondary-button" disabled={submitting} onClick={() => setReviewOpen(false)}>Back to ticket</button><button className={`primary-button ${side === 'SELL' ? 'button-sell' : ''}`} disabled={submitting} onClick={submitOrder}>{submitting ? 'Submitting…' : 'Place order'}</button></div>
      {error && <p className="inline-error" role="alert">{error}</p>}
    </Modal>}

    {result && <Modal title="Order submitted" eyebrow="CONFIRMATION" onClose={resetOrder}>
      <div className="order-detail-head"><div><strong>{result.stock_symbol}</strong><span>{result.side} {orderTypeNames[result.order_type]}</span></div><StatusBadge status={result.status}/></div>
      <div className="detail-grid">
        <div><span>Order ID</span><strong>#{result.id}</strong></div>
        <div><span>Quantity</span><strong>{formatQuantity(result.quantity)}</strong></div>
        <div><span>Filled</span><strong>{formatQuantity(result.filled_quantity)}</strong></div>
        <div><span>Remaining</span><strong>{formatQuantity(result.remaining_quantity)}</strong></div>
        <div><span>Average fill</span><strong>{result.average_fill_price == null ? '—' : formatCurrency(result.average_fill_price)}</strong></div>
        <div><span>Fees paid</span><strong>{result.actual_fees == null ? 'Not yet available' : formatCurrency(result.actual_fees)}</strong></div>
        {result.actual_fees == null && result.estimated_fees != null && <div><span>Estimated fees</span><strong>{formatCurrency(result.estimated_fees)}</strong></div>}
        <div><span>Submitted</span><strong>{formatDateTime(result.created_at)}</strong></div>
      </div>
      <div className="modal-actions"><button className="primary-button" onClick={resetOrder}>Done</button></div>
    </Modal>}
  </section>
}
