import { useState } from 'react'
import { Icon } from '../common/ui'
import { formatCurrency } from '../../utils/format'

const links = [
  ['dashboard', 'Dashboard', 'dashboard'],
  ['markets', 'Markets', 'markets'],
  ['watchlist', 'Watchlist', 'watchlist'],
  ['portfolio', 'Portfolio', 'portfolio'],
  ['orders', 'Orders', 'orders'],
  ['wallet', 'Balance', 'wallet'],
  ['profile', 'Profile', 'profile'],
]

export default function TradingShell({ children, active, onNavigate, user, walletBalance, stocks, onLogout, onSelectStock }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [query, setQuery] = useState('')
  const matches = query.trim() ? stocks.filter((stock) => `${stock.symbol} ${stock.company_name}`.toLowerCase().includes(query.trim().toLowerCase())).slice(0, 6) : []
  const select = (symbol) => { onSelectStock(symbol); setQuery(''); onNavigate('markets') }
  const navigate = (key) => { onNavigate(key); setMenuOpen(false) }

  return <div className="app-frame">
    <header className="topbar">
      <button className="mobile-menu icon-button" aria-label="Open navigation" onClick={() => setMenuOpen(!menuOpen)}><Icon name="menu" /></button>
      <button className="brand" onClick={() => navigate('dashboard')} aria-label="TradeX dashboard"><span className="brand-mark">T</span><span>Trade<span className="brand-accent">X</span></span></button>
      <div className="global-search"><Icon name="search" size={17} /><input aria-label="Search stocks and companies" placeholder="Search stocks, companies..." value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && matches[0] && select(matches[0].symbol)} />{query && <div className="search-results">{matches.length ? matches.map((stock) => <button key={stock.symbol} onClick={() => select(stock.symbol)}><strong>{stock.symbol}</strong><span>{stock.company_name}</span><b>{formatCurrency(stock.current_price)}</b></button>) : <span className="search-empty">No matching instruments</span>}</div>}</div>
      <div className="topbar-right"><div className="balance-chip"><small>AVAILABLE FUNDS</small><strong>{formatCurrency(walletBalance)}</strong></div><button className="profile-chip" onClick={() => navigate('profile')} aria-label="Open profile"><span className="avatar">{(user?.name || 'T').charAt(0).toUpperCase()}</span><span className="profile-name">{user?.name || 'Trader'}</span></button><button className="logout-button" onClick={onLogout} aria-label="Log out"><Icon name="logout" size={17} /><span>Logout</span></button></div>
    </header>
    <div className="workspace">
      <aside className={`sidebar${menuOpen ? ' sidebar-open' : ''}`}><div className="sidebar-caption">WORKSPACE</div><nav aria-label="Main navigation">{links.map(([key, label, icon]) => <button key={key} className={`nav-link${active === key ? ' active' : ''}`} onClick={() => navigate(key)}><Icon name={icon} /><span>{label}</span>{key === 'watchlist' && <span className="nav-shortcut">⌘</span>}</button>)}</nav><div className="sidebar-bottom"><div className="account-card"><span className="account-dot"/><strong>TradeX account</strong><span>Account funds · INR</span></div><button className="nav-link logout-mobile" onClick={onLogout}><Icon name="logout"/><span>Logout</span></button><small className="sidebar-version">TRADEX · TRADING</small></div></aside>
      {menuOpen && <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setMenuOpen(false)} />}
      <main className="main-content">{children}</main>
    </div>
    <nav className="bottom-nav" aria-label="Mobile navigation">{links.slice(0, 5).map(([key, label, icon]) => <button key={key} className={active === key ? 'active' : ''} onClick={() => navigate(key)}><Icon name={icon} size={19}/><span>{label === 'Dashboard' ? 'Home' : label}</span></button>)}</nav>
  </div>
}
