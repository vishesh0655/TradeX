import { useEffect, useState } from 'react'
import Login from './Login'

function App() {
  const [stocks, setStocks] = useState([])
  const [isLoggedIn, setIsLoggedIn] = useState(!!localStorage.getItem('token'))

  useEffect(() => {
    fetch('http://127.0.0.1:8000/stocks')
      .then((response) => response.json())
      .then((data) => setStocks(data.stocks))
      .catch((error) => console.error('Error fetching stocks:', error))
  }, [])

  const handleLogout = () => {
    localStorage.removeItem('token')
    setIsLoggedIn(false)
  }

  if (!isLoggedIn) {
    return <Login onLoginSuccess={() => setIsLoggedIn(true)} />
  }

  return (
    <div>
      <h1>TradeX</h1>
      <button onClick={handleLogout}>Logout</button>
      <h2>Available Stocks</h2>
      <ul>
        {stocks.map((stock) => (
          <li key={stock.symbol}>
            {stock.symbol} — {stock.company_name} — ₹{stock.current_price}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default App