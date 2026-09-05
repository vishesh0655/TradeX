import { useEffect, useState } from 'react'

function Portfolio({ refreshTrigger }) {
  const [holdings, setHoldings] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    const token = localStorage.getItem('token')

    fetch(`${import.meta.env.VITE_API_URL}/holdings`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((response) => {
        if (!response.ok) throw new Error('Failed to load holdings')
        return response.json()
      })
      .then((data) => setHoldings(data))
      .catch((err) => setError(err.message))
  }, [refreshTrigger])

  if (error) return <p style={{ color: 'red' }}>{error}</p>

  return (
    <div>
      <h2>My Holdings</h2>
      {holdings.length === 0 ? (
        <p>You don't own any stocks yet.</p>
      ) : (
        <table border="1" cellPadding="8">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Qty</th>
              <th>Avg Buy Price</th>
              <th>Current Price</th>
              <th>Invested</th>
              <th>Current Value</th>
              <th>P&L</th>
              <th>P&L %</th>
            </tr>
          </thead>
          <tbody>
            {holdings.map((h) => (
              <tr key={h.stock_symbol}>
                <td>{h.stock_symbol}</td>
                <td>{h.quantity}</td>
                <td>₹{h.average_buy_price}</td>
                <td>₹{h.current_price}</td>
                <td>₹{h.invested_value}</td>
                <td>₹{h.current_value}</td>
                <td style={{ color: h.profit_loss >= 0 ? 'green' : 'red' }}>
                  ₹{h.profit_loss}
                </td>
                <td style={{ color: h.profit_loss_percent >= 0 ? 'green' : 'red' }}>
                  {h.profit_loss_percent}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default Portfolio