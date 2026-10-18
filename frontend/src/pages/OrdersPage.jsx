import { useEffect, useState } from 'react'
import { getExecutions, getOrderEvents } from '../api/orders'
import { DataTable, EmptyState, Modal, StatusBadge, TimeLabel } from '../components/common/ui'
import { formatCurrency, formatDateTime, formatQuantity } from '../utils/format'

const filters = [['ALL', 'All'], ['OPEN', 'Open'], ['PARTIALLY_FILLED', 'Partial'], ['FILLED', 'Filled'], ['CANCELLED', 'Cancelled'], ['REJECTED', 'Rejected']]

export default function OrdersPage({ orders, loading, refresh }) {
  const [filter, setFilter] = useState('ALL')
  const [selected, setSelected] = useState(null)
  const [events, setEvents] = useState([])
  const [executions, setExecutions] = useState([])
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const visible = filter === 'ALL' ? orders : orders.filter((order) => order.status === filter)

  useEffect(() => {
    if (!selected) return
    let active = true
    Promise.all([getOrderEvents(selected.id), getExecutions(selected.id)])
      .then(([eventData, fillData]) => { if (active) { setEvents(eventData); setExecutions(fillData) } })
      .catch((error) => { if (active) setDetailError(error.message) })
      .finally(() => { if (active) setDetailLoading(false) })
    return () => { active = false }
  }, [selected, refresh])

  const dismiss = () => { setSelected(null); setEvents([]); setExecutions([]); setDetailLoading(false) }
  const openOrder = (order) => { setDetailLoading(true); setDetailError(''); setEvents([]); setExecutions([]); setSelected(order) }
  return <div className="page-stack"><div className="page-title-row"><div><span className="eyebrow">PAPER ORDER BOOK</span><h1>Orders</h1><p>Track order status and simulated fills from the backend.</p></div><button className="secondary-button" onClick={refresh}>Refresh</button></div><section className="content-card"><div className="filter-tabs" role="tablist" aria-label="Filter orders">{filters.map(([value, label]) => <button key={value} role="tab" aria-selected={filter === value} className={filter === value ? 'active' : ''} onClick={() => setFilter(value)}>{label}{value === 'ALL' && <span>{orders.length}</span>}</button>)}</div>{loading ? <div className="loading-block">Loading orders…</div> : visible.length ? <DataTable><thead><tr><th>Order</th><th>Instrument</th><th>Side</th><th>Type</th><th>Qty / Filled</th><th>Average fill</th><th>Status</th><th>Placed</th><th /></tr></thead><tbody>{visible.map((order) => <tr key={order.id}><td className="order-id">#{order.id}</td><td><strong>{order.stock_symbol}</strong></td><td className={order.side === 'BUY' ? 'positive' : 'negative'}>{order.side}</td><td>{order.order_type}</td><td className="numeric">{formatQuantity(order.filled_quantity)} / {formatQuantity(order.quantity)}</td><td className="numeric">{order.average_fill_price == null ? '—' : formatCurrency(order.average_fill_price)}</td><td><StatusBadge status={order.status}/></td><td><TimeLabel value={order.created_at}/></td><td><button className="mini-button" onClick={() => openOrder(order)}>View</button></td></tr>)}</tbody></DataTable> : <EmptyState title={filter === 'ALL' ? 'No orders yet.' : `No ${filter.toLowerCase().replaceAll('_', ' ')} orders.`} detail="Your paper order activity will appear here."/>}</section><p className="data-footnote">Orders are submitted to simulated paper execution. Cancellation and modification are not currently supported by the backend.</p>
    {selected && <Modal title={`Order #${selected.id}`} eyebrow="ORDER DETAILS" onClose={dismiss} wide><div className="order-detail-head"><div><strong>{selected.stock_symbol}</strong><span>{selected.side} {selected.order_type}</span></div><StatusBadge status={selected.status}/></div><div className="detail-grid"><div><span>Quantity</span><strong>{formatQuantity(selected.quantity)}</strong></div><div><span>Filled</span><strong>{formatQuantity(selected.filled_quantity)}</strong></div><div><span>Remaining</span><strong>{formatQuantity(Math.max(0, selected.quantity - selected.filled_quantity))}</strong></div><div><span>Average fill</span><strong>{selected.average_fill_price == null ? '—' : formatCurrency(selected.average_fill_price)}</strong></div><div><span>Limit price</span><strong>{selected.limit_price == null ? '—' : formatCurrency(selected.limit_price)}</strong></div><div><span>Created</span><strong>{formatDateTime(selected.created_at)}</strong></div></div>{detailLoading ? <div className="loading-block">Loading order activity…</div> : detailError ? <p className="inline-error" role="alert">{detailError}</p> : <><h3 className="subsection-title">Order events</h3>{events.length ? <ol className="event-timeline">{events.map((event) => <li key={event.id}><i/><div><strong>{event.event_type.replaceAll('_', ' ')}</strong><span>{formatDateTime(event.created_at)}</span></div></li>)}</ol> : <p className="muted-copy">No event records are available for this order.</p>}<h3 className="subsection-title">Executions</h3>{executions.length ? <DataTable><thead><tr><th>Execution</th><th>Quantity</th><th>Price</th><th>Time</th></tr></thead><tbody>{executions.map((fill) => <tr key={fill.id}><td>#{fill.id}</td><td>{formatQuantity(fill.quantity)}</td><td>{formatCurrency(fill.execution_price)}</td><td>{formatDateTime(fill.executed_at)}</td></tr>)}</tbody></DataTable> : <p className="muted-copy">No simulated fills recorded.</p>}</>}</Modal>}
  </div>
}
