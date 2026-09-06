import { useEffect, useState } from 'react'

function OrderHistory({ refreshTrigger }) {
  const [orders, setOrders] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    const token = localStorage.getItem('token')

    fetch(`${import.meta.env.VITE_API_URL}/orders`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((response) => {
        if (!response.ok) throw new Error('Failed to load order history')
        return response.json()
      })
      .then((data) => setOrders(data))
      .catch((err) => setError(err.message))
  }, [refreshTrigger])

  if (error) return <p className="error-text">{error}</p>

  return (
    <div>
      <h2>Order History</h2>
      {orders.length === 0 ? (
        <p>No orders placed yet.</p>
      ) : (
        <table border="1" cellPadding="8">
          <thead>
            <tr>
              <th>Type</th>
              <th>Stock ID</th>
              <th>Qty</th>
              <th>Price/Share</th>
              <th>Total</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((order) => (
              <tr key={order.id}>
                <td style={{ color: order.order_type === 'BUY' ? '#4ade80' : '#f87171' }}>
                  {order.order_type}
                </td>
                <td>{order.stock_id}</td>
                <td>{order.quantity}</td>
                <td>₹{order.price_per_share}</td>
                <td>₹{order.total_amount}</td>
                <td>{order.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default OrderHistory