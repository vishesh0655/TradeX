import { useEffect, useState } from 'react'
import Login from './Login'
import Register from './Register'
import PhoneLoginPage from './PhoneLoginPage'
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

  // Handle successful phone OTP verification
  const handlePhoneLogin = async (firebaseIdToken, rememberMe) => {
    const response = await fetch(
      `${import.meta.env.VITE_API_URL}/auth/phone`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          credential: firebaseIdToken,
        }),
      }
    )

    const data = await response.json()

    if (!response.ok) {
      throw new Error(data.detail || 'Phone login failed')
    }

    if (rememberMe) {
      localStorage.setItem('token', data.access_token)
      sessionStorage.removeItem('token')
    } else {
      sessionStorage.setItem('token', data.access_token)
      localStorage.removeItem('token')
    }

    setAuthView('login')
    setIsLoggedIn(true)
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

  // Show authentication pages
  if (!isLoggedIn) {
    if (authView === 'register') {
      return (
        <Register
          onRegisterSuccess={() => setAuthView('login')}
          onSwitchToLogin={() => setAuthView('login')}
          onSwitchToPhone={() => setAuthView('phone')}
        />
      )
    }

    if (authView === 'phone') {
      return (
        <PhoneLoginPage
          onPhoneLogin={handlePhoneLogin}
          onBack={() => setAuthView('login')}
        />
      )
    }

    return (
      <Login
        onLoginSuccess={() => setIsLoggedIn(true)}
        onSwitchToRegister={() => setAuthView('register')}
        onSwitchToPhone={() => setAuthView('phone')}
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