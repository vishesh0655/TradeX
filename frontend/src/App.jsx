
import { useEffect, useState } from 'react'
import Login from './Login'
import Register from './Register'
import Portfolio from './Portfolio'
import OrderHistory from './OrderHistory'
import Trade from './Trade'

function App() {
  const [stocks, setStocks] = useState([])
  const [walletBalance, setWalletBalance] = useState(null)

  const [isLoggedIn, setIsLoggedIn] = useState(
    !!(
      localStorage.getItem('token') ||
      sessionStorage.getItem('token')
    )
  )

  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [authView, setAuthView] = useState('login')

  const handleLogout = () => {
    localStorage.removeItem('token')
    sessionStorage.removeItem('token')

    setWalletBalance(null)
    setIsLoggedIn(false)
    setAuthView('login')
  }

  // Fetch available stocks
  useEffect(() => {
    fetch(`${import.meta.env.VITE_API_URL}/stocks`)
      .then((response) => {
        if (!response.ok) {
          throw new Error('Failed to fetch stocks')
        }
        return response.json()
      })
      .then((data) => {
        setStocks(data.stocks)
      })
      .catch((error) => {
        console.error('Error fetching stocks:', error)
      })
  }, [])

  // Fetch logged-in user information
  useEffect(() => {
    if (!isLoggedIn) return

    const token =
      localStorage.getItem('token') ||
      sessionStorage.getItem('token')

    if (!token) {
      handleLogout()
      return
    }

    fetch(`${import.meta.env.VITE_API_URL}/me`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    })
      .then((response) => {
        if (response.status === 401) {
          handleLogout()
          return null
        }

        if (!response.ok) {
          throw new Error('Failed to fetch user information')
        }

        return response.json()
      })
      .then((data) => {
        if (data) {
          setWalletBalance(data.wallet_balance)
        }
      })
      .catch((error) => {
        console.error('Error fetching user info:', error)
      })
  }, [isLoggedIn, refreshTrigger])

  // Show login or registration page
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

  // Main TradeX dashboard
  return (
    <div>
      <h1>TradeX</h1>

      <button onClick={handleLogout}>
        Logout
      </button>

      {walletBalance !== null && (
        <h3>
          Wallet Balance: ₹{walletBalance.toFixed(2)}
        </h3>
      )}

      <Trade
        onTradeComplete={() =>
          setRefreshTrigger((n) => n + 1)
        }
      />

      <Portfolio
        refreshTrigger={refreshTrigger}
      />

      <OrderHistory
        refreshTrigger={refreshTrigger}
      />

      <h2>Available Stocks</h2>

      <ul>
        {stocks.map((stock) => (
          <li key={stock.symbol}>
            {stock.symbol} — {stock.company_name} — ₹
            {stock.current_price}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default App