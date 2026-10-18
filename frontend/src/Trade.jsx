import { useState } from 'react'
import { placeOrder as submitPaperOrder } from './api/orders'
import { getToken } from './api/client'

function Trade({ onTradeComplete }) {
  const [symbol, setSymbol] = useState('')
  const [quantity, setQuantity] = useState('')
  const [message, setMessage] = useState('')
  const [isError, setIsError] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const placeOrder = async (side) => {
    setMessage('')
    setIsError(false)

    const token = getToken()

    if (!token) {
      setMessage('Please log in again to place an order.')
      setIsError(true)
      return
    }

    const cleanSymbol = symbol.trim().toUpperCase()
    const cleanQuantity = Number.parseInt(quantity, 10)

    if (!cleanSymbol) {
      setMessage('Enter a stock symbol.')
      setIsError(true)
      return
    }

    if (!Number.isInteger(cleanQuantity) || cleanQuantity <= 0) {
      setMessage('Quantity must be a positive whole number.')
      setIsError(true)
      return
    }

    setIsSubmitting(true)

    try {
      const data = await submitPaperOrder({
        stock_symbol: cleanSymbol,
        side,
        order_type: 'MARKET',
        quantity: cleanQuantity,
      })

      setMessage(
        `${side === 'BUY' ? 'Bought' : 'Sold'} ${data.filled_quantity} ${cleanSymbol} @ ₹${data.average_fill_price}`
      )
      setIsError(false)
      setSymbol('')
      setQuantity('')
      onTradeComplete()
    } catch (err) {
      setMessage(err.message)
      setIsError(true)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div>
      <h2>Trade</h2>
      <input
        type="text"
        placeholder="Stock Symbol (e.g. TCS)"
        value={symbol}
        onChange={(e) => setSymbol(e.target.value)}
        disabled={isSubmitting}
      />
      <input
        type="number"
        placeholder="Quantity"
        value={quantity}
        onChange={(e) => setQuantity(e.target.value)}
        min="1"
        step="1"
        disabled={isSubmitting}
      />
      <button onClick={() => placeOrder('BUY')} disabled={isSubmitting}>
        {isSubmitting ? 'Processing...' : 'Buy'}
      </button>
      <button onClick={() => placeOrder('SELL')} disabled={isSubmitting}>
        {isSubmitting ? 'Processing...' : 'Sell'}
      </button>
      {message && (
        <p style={{ color: isError ? 'red' : 'green' }}>{message}</p>
      )}
    </div>
  )
}

export default Trade
