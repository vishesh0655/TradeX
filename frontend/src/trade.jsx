import { useState } from 'react'

function Trade({ onTradeComplete }) {
  const [symbol, setSymbol] = useState('')
  const [quantity, setQuantity] = useState('')
  const [message, setMessage] = useState('')
  const [isError, setIsError] = useState(false)

  const placeOrder = async (orderType) => {
    setMessage('')
    setIsError(false)

    const token = localStorage.getItem('token')

    try {
      const response = await fetch(`http://127.0.0.1:8000/orders/${orderType}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          stock_symbol: symbol.toUpperCase(),
          quantity: parseInt(quantity, 10),
        }),
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || 'Order failed')
      }

      setMessage(
        `${orderType === 'buy' ? 'Bought' : 'Sold'} ${data.quantity} ${symbol.toUpperCase()} @ ₹${data.price_per_share}`
      )
      setIsError(false)
      setSymbol('')
      setQuantity('')
      onTradeComplete()
    } catch (err) {
      setMessage(err.message)
      setIsError(true)
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
      />
      <input
        type="number"
        placeholder="Quantity"
        value={quantity}
        onChange={(e) => setQuantity(e.target.value)}
        min="1"
      />
      <button onClick={() => placeOrder('buy')}>Buy</button>
      <button onClick={() => placeOrder('sell')}>Sell</button>
      {message && (
        <p style={{ color: isError ? 'red' : 'green' }}>{message}</p>
      )}
    </div>
  )
}

export default Trade