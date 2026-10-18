import { useCallback, useEffect, useMemo, useState } from 'react'
import Login from './Login'
import Register from './Register'
import PhoneLoginPage from './PhoneLoginPage'
import TradingShell from './components/layout/TradingShell'
import { Toast } from './components/common/ui'
import DashboardPage from './pages/DashboardPage'
import MarketsPage from './pages/MarketsPage'
import PortfolioPage from './pages/PortfolioPage'
import OrdersPage from './pages/OrdersPage'
import WalletPage from './pages/WalletPage'
import WatchlistPage from './pages/WatchlistPage'
import ProfilePage from './pages/ProfilePage'
import { getStocks } from './api/stocks'
import { signInWithPhone } from './api/auth'
import { getProfile, getHoldings } from './api/portfolio'
import { getOrders, placeOrder } from './api/orders'
import { getWallet, getWalletTransactions } from './api/wallet'
import { addToWatchlist, getWatchlist, removeFromWatchlist } from './api/watchlist'
import { getToken } from './api/client'
import './App.css'

function App() {
  const [authenticated, setAuthenticated] = useState(() => Boolean(getToken()))
  const [authView, setAuthView] = useState('login')
  const [activePage, setActivePage] = useState('dashboard')
  const [user, setUser] = useState(null)
  const [stocks, setStocks] = useState([])
  const [holdings, setHoldings] = useState([])
  const [orders, setOrders] = useState([])
  const [wallet, setWallet] = useState(null)
  const [transactions, setTransactions] = useState([])
  const [watchlist, setWatchlist] = useState([])
  const [selectedSymbol, setSelectedSymbol] = useState('')
  const [loading, setLoading] = useState(true)
  const [sectionErrors, setSectionErrors] = useState({})
  const [refreshId, setRefreshId] = useState(0)
  const [toasts, setToasts] = useState([])

  const dismissToast = useCallback((id) => setToasts((current) => current.filter((item) => item.id !== id)), [])
  const notify = useCallback((message, type = 'success') => {
    const id = `${Date.now()}-${Math.random()}`
    setToasts((items) => [...items, { id, message, type }])
  }, [])

  useEffect(() => {
    if (!authenticated || !getToken()) return undefined
    let active = true
    const load = async () => {
      const results = await Promise.allSettled([
        getStocks(), getProfile(), getHoldings(), getOrders(), getWallet(), getWalletTransactions(), getWatchlist(),
      ])
      if (!active) return
      const [market, profile, positions, orderRows, walletRow, ledger, saved] = results
      const errors = {}
      if (market.status === 'fulfilled') {
        setStocks(market.value)
        setSelectedSymbol((current) => current || market.value[0]?.symbol || '')
      } else errors.market = market.reason.message
      if (profile.status === 'fulfilled') setUser(profile.value)
      else errors.profile = profile.reason.message
      if (positions.status === 'fulfilled') setHoldings(positions.value)
      else errors.portfolio = positions.reason.message
      if (orderRows.status === 'fulfilled') setOrders(orderRows.value)
      else errors.orders = orderRows.reason.message
      if (walletRow.status === 'fulfilled') setWallet(walletRow.value)
      else if (profile.status === 'fulfilled') setWallet({ balance: profile.value.wallet_balance, currency: 'INR' })
      else errors.wallet = walletRow.reason.message
      if (ledger.status === 'fulfilled') setTransactions(ledger.value)
      else errors.transactions = ledger.reason.message
      if (saved.status === 'fulfilled') setWatchlist(saved.value)
      else errors.watchlist = saved.reason.message
      setSectionErrors(errors)
      setLoading(false)
    }
    load()
    return () => { active = false }
  }, [authenticated, refreshId])

  useEffect(() => {
    const onUnauthorized = () => {
      setAuthenticated(false)
      setUser(null)
      setWallet(null)
      setHoldings([])
      setOrders([])
      setTransactions([])
      setWatchlist([])
      setAuthView('login')
      notify('Your session expired. Please sign in again.', 'error')
    }
    window.addEventListener('tradex:unauthorized', onUnauthorized)
    return () => window.removeEventListener('tradex:unauthorized', onUnauthorized)
  }, [notify])

  const handleLogout = useCallback(() => {
    localStorage.removeItem('token')
    sessionStorage.removeItem('token')
    setAuthenticated(false)
    setUser(null)
    setWallet(null)
    setHoldings([])
    setOrders([])
    setTransactions([])
    setWatchlist([])
    setAuthView('login')
  }, [])

  const handleLoginSuccess = useCallback(() => {
    setLoading(true)
    setAuthenticated(true)
  }, [])

  const handlePhoneLogin = async (firebaseIdToken, rememberMe) => {
    const data = await signInWithPhone(firebaseIdToken)
    if (rememberMe) { localStorage.setItem('token', data.access_token); sessionStorage.removeItem('token') }
    else { sessionStorage.setItem('token', data.access_token); localStorage.removeItem('token') }
    setAuthView('login'); handleLoginSuccess()
  }

  const submitOrder = useCallback(async (payload) => {
    const order = await placeOrder(payload)
    notify(`${order.stock_symbol} ${order.side} order submitted · ${order.status.replaceAll('_', ' ')}`)
    setRefreshId((value) => value + 1)
    return order
  }, [notify])

  const toggleWatchlist = useCallback(async (symbol) => {
    const exists = watchlist.some((item) => item.symbol === symbol)
    try {
      if (exists) {
        await removeFromWatchlist(symbol)
        setWatchlist((items) => items.filter((item) => item.symbol !== symbol))
        notify(`${symbol} removed from watchlist`)
      } else {
        const item = await addToWatchlist(symbol)
        setWatchlist((items) => [...items, item])
        notify(`${symbol} added to watchlist`)
      }
    } catch (error) { notify(error.message, 'error') }
  }, [notify, watchlist])

  const walletBalance = Number(wallet?.balance ?? user?.wallet_balance ?? 0)
  const activePageTitle = useMemo(() => ({ dashboard: 'Dashboard', markets: 'Markets', watchlist: 'Watchlist', portfolio: 'Portfolio', orders: 'Orders', wallet: 'Virtual wallet', profile: 'Profile' })[activePage], [activePage])
  const pageErrorKeys = {
    dashboard: ['profile', 'market', 'portfolio', 'orders'],
    markets: ['market'],
    watchlist: ['watchlist'],
    portfolio: ['portfolio'],
    orders: ['orders'],
    wallet: ['wallet', 'transactions'],
    profile: ['profile'],
  }
  const activeErrors = (pageErrorKeys[activePage] || []).map((key) => sectionErrors[key]).filter(Boolean)

  if (!authenticated) {
    if (authView === 'register') return <Register onRegisterSuccess={() => setAuthView('login')} onSwitchToLogin={() => setAuthView('login')} onSwitchToPhone={() => setAuthView('phone')} />
    if (authView === 'phone') return <PhoneLoginPage onPhoneLogin={handlePhoneLogin} onBack={() => setAuthView('login')} />
    return <Login onLoginSuccess={handleLoginSuccess} onSwitchToRegister={() => setAuthView('register')} onSwitchToPhone={() => setAuthView('phone')} />
  }

  const common = { stocks, holdings, orders, walletBalance, watchlist, loading, onNavigate: setActivePage }
  return <>
    <TradingShell active={activePage} onNavigate={setActivePage} user={user} walletBalance={walletBalance} stocks={stocks} onLogout={handleLogout} onSelectStock={setSelectedSymbol}>
      {activeErrors.map((error, index) => <div key={`${activePage}-${index}`} className="page-error" role="alert">{error} <button onClick={() => setRefreshId((value) => value + 1)}>Retry</button></div>)}
      <div className="page-heading-mobile"><span>{activePageTitle}</span><span className="mobile-paper">PAPER</span></div>
      {activePage === 'dashboard' && <DashboardPage {...common} selectedSymbol={selectedSymbol} setSelectedSymbol={setSelectedSymbol} onPlaceOrder={submitOrder} onToggleWatchlist={toggleWatchlist} />}
      {activePage === 'markets' && <MarketsPage stocks={stocks} selectedSymbol={selectedSymbol} setSelectedSymbol={setSelectedSymbol} watchlist={watchlist} onToggleWatchlist={toggleWatchlist} loading={loading} walletBalance={walletBalance} holdings={holdings} onPlaceOrder={submitOrder} />}
      {activePage === 'watchlist' && <WatchlistPage watchlist={watchlist} onToggleWatchlist={toggleWatchlist} onSelectStock={setSelectedSymbol} stocks={stocks} loading={loading} onNavigate={setActivePage} />}
      {activePage === 'portfolio' && <PortfolioPage holdings={holdings} walletBalance={walletBalance} loading={loading} onNavigate={setActivePage} />}
      {activePage === 'orders' && <OrdersPage orders={orders} loading={loading} refresh={() => setRefreshId((value) => value + 1)} />}
      {activePage === 'wallet' && <WalletPage walletBalance={walletBalance} transactions={transactions} loading={loading} />}
      {activePage === 'profile' && <ProfilePage user={user} walletBalance={walletBalance} onLogout={handleLogout} />}
    </TradingShell>
    <Toast items={toasts} dismiss={dismissToast} />
  </>
}

export default App
