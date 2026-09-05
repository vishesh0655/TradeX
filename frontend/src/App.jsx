import { useEffect, useState } from 'react'
import Login from './Login'
import Register from './Register'
import Portfolio from './Portfolio'
import Trade from './Trade'

function App() {
  const [stocks, setStocks] = useState([])
  const [isLoggedIn, setIsLoggedIn] = useState(!!localStorage.getItem('token'))
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [authView, setAuthView] = useState('login')

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
    if (authView === 'register') {
      return (
        <Register
          onRegisterSuccess={() => setAuthView('login')}
          onSwitchToLogin={() => setAuthView('login')}
        />
      )
    }
    return (
      <Login
        onLoginSuccess={() => setIsLoggedIn(true)}
        onSwitchToRegister={() => setAuthView('register')}
      />
    )
  }

  return (
    <div>
      <h1>TradeX</h1>
      <button onClick={handleLogout}>Logout</button>
      <Trade onTradeComplete={() => setRefreshTrigger((n) => n + 1)} />
      <Portfolio refreshTrigger={refreshTrigger} />
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