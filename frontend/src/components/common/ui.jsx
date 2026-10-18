import { useEffect } from 'react'
import { formatDateTime } from '../../utils/format'

export function Icon({ name, size = 18 }) {
  const paths = {
    dashboard: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></>,
    markets: <><path d="M3 3v18h18"/><path d="m7 14 4-4 4 3 6-7"/></>,
    portfolio: <><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z"/></>,
    orders: <><path d="M8 6h13M8 12h13M8 18h13"/><path d="M3 6h.01M3 12h.01M3 18h.01"/></>,
    wallet: <><rect x="3" y="5" width="18" height="15" rx="2"/><path d="M3 9h18M16 14h2"/><path d="M6 5V3h13"/></>,
    watchlist: <><path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9L12 3Z"/></>,
    profile: <><circle cx="12" cy="8" r="4"/><path d="M5 21a7 7 0 0 1 14 0"/></>,
    search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
    logout: <><path d="M10 17l5-5-5-5M15 12H3"/><path d="M12 3h6a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-6"/></>,
    close: <><path d="m18 6-12 12M6 6l12 12"/></>,
    menu: <><path d="M4 6h16M4 12h16M4 18h16"/></>,
    arrow: <><path d="M5 12h14M13 6l6 6-6 6"/></>,
  }
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{paths[name] || paths.dashboard}</svg>
}

export function PaperBadge() {
  return <span className="paper-badge"><i /> PAPER MODE <span>VIRTUAL FUNDS</span></span>
}

export function MetricCard({ label, value, note, tone = 'neutral', icon }) {
  return <article className="metric-card"><div className="metric-top"><span>{label}</span>{icon && <span className="metric-icon"><Icon name={icon} /></span>}</div><strong className={tone}>{value}</strong>{note && <small>{note}</small>}</article>
}

export function EmptyState({ title, detail, action }) {
  return <div className="empty-state"><div className="empty-mark"><Icon name="markets" size={20} /></div><strong>{title}</strong><p>{detail}</p>{action}</div>
}

export function StatusBadge({ status }) {
  return <span className={`status-badge status-${String(status || 'unknown').toLowerCase().replaceAll('_', '-')}`}>{String(status || 'UNKNOWN').replaceAll('_', ' ')}</span>
}

export function Modal({ title, eyebrow, onClose, children, wide = false }) {
  useEffect(() => {
    const closeOnEscape = (event) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', closeOnEscape)
    document.body.classList.add('modal-open')
    return () => { window.removeEventListener('keydown', closeOnEscape); document.body.classList.remove('modal-open') }
  }, [onClose])
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><section className={`modal-card${wide ? ' modal-wide' : ''}`} role="dialog" aria-modal="true" aria-labelledby="modal-title"><div className="modal-heading"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h2 id="modal-title">{title}</h2></div><button className="icon-button" onClick={onClose} aria-label="Close dialog"><Icon name="close" /></button></div>{children}</section></div>
}

export function Toast({ items, dismiss }) {
  useEffect(() => {
    const timers = items.map((item) => setTimeout(() => dismiss(item.id), 4500))
    return () => timers.forEach(clearTimeout)
  }, [items, dismiss])
  return <div className="toast-region" aria-live="polite">{items.map((item) => <div key={item.id} className={`toast toast-${item.type || 'success'}`}><span className="toast-mark">{item.type === 'error' ? '!' : '✓'}</span><span>{item.message}</span><button onClick={() => dismiss(item.id)} aria-label="Dismiss notification"><Icon name="close" size={15} /></button></div>)}</div>
}

export function DataTable({ children, className = '' }) {
  return <div className={`table-wrap ${className}`}><table className="data-table">{children}</table></div>
}

export function TimeLabel({ value }) {
  return <time dateTime={value || undefined}>{formatDateTime(value)}</time>
}

