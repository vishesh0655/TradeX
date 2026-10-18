import { useEffect, useState } from 'react'
import { cancelOrder, getExecutions, getOrderEvents, modifyOrder } from '../api/orders'
import { DataTable, EmptyState, Modal, StatusBadge } from '../components/common/ui'
import { formatCurrency, formatDateTime, formatQuantity } from '../utils/format'

const filters = [
  ['ALL', 'All'], ['OPEN', 'Open'], ['PARTIALLY_FILLED', 'Partial'], ['FILLED', 'Filled'],
  ['CANCEL_PENDING', 'Cancel pending'], ['CANCELLED', 'Cancelled'], ['REJECTED', 'Rejected'], ['EXPIRED', 'Expired'],
]
const cancellable = (status) => ['OPEN', 'PARTIALLY_FILLED'].includes(status)
const modifiable = (order) => order.status === 'OPEN' && order.filled_quantity === 0 && !order.stop_triggered

export default function OrdersPage({ orders, loading, refresh, error, notify }) {
  const [filter, setFilter] = useState('ALL')
  const [selected, setSelected] = useState(null)
  const [events, setEvents] = useState([])
  const [executions, setExecutions] = useState([])
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [mutationId, setMutationId] = useState(null)
  const [confirmCancel, setConfirmCancel] = useState(null)
  const [modifyTarget, setModifyTarget] = useState(null)
  const [modifyValues, setModifyValues] = useState({ quantity: '', limit_price: '', stop_price: '' })
  const [modifyError, setModifyError] = useState('')
  const visible = filter === 'ALL' ? orders : orders.filter((order) => order.status === filter)

  useEffect(() => {
    if (!selected) return undefined
    let active = true
    Promise.all([getOrderEvents(selected.id), getExecutions(selected.id)])
      .then(([eventData, fillData]) => { if (active) { setEvents(eventData); setExecutions(fillData); setDetailError('') } })
      .catch((requestError) => { if (active) setDetailError(requestError.message || 'Order activity could not be loaded.') })
      .finally(() => { if (active) setDetailLoading(false) })
    return () => { active = false }
  }, [selected, refresh])

  const loadDetails = async (order) => {
    setDetailLoading(true)
    setDetailError('')
    try {
      const [eventData, fillData] = await Promise.all([getOrderEvents(order.id), getExecutions(order.id)])
      setEvents(eventData)
      setExecutions(fillData)
    } catch (requestError) { setDetailError(requestError.message || 'Order activity could not be loaded.') }
    finally { setDetailLoading(false) }
  }
  const openOrder = (order) => { setDetailLoading(true); setEvents([]); setExecutions([]); setDetailError(''); setSelected(order) }
  const closeDetails = () => { setSelected(null); setEvents([]); setExecutions([]) }
  const doCancel = async () => {
    const order = confirmCancel
    setMutationId(order.id)
    try {
      const updatedOrder = await cancelOrder(order.id)
      notify(`Order #${order.id} cancelled`)
      setConfirmCancel(null)
      refresh()
      if (selected?.id === order.id) setSelected(updatedOrder)
    } catch (requestError) { notify(requestError.message || 'Order could not be cancelled.', 'error') }
    finally { setMutationId(null) }
  }
  const startModify = (order) => {
    setModifyTarget(order)
    setModifyValues({ quantity: String(order.quantity), limit_price: order.limit_price ?? '', stop_price: order.stop_price ?? '' })
    setModifyError('')
  }
  const doModify = async (event) => {
    event.preventDefault()
    const order = modifyTarget
    const changes = { quantity: Number(modifyValues.quantity) }
    if (['LIMIT', 'STOP_LIMIT'].includes(order.order_type)) changes.limit_price = Number(modifyValues.limit_price)
    if (['STOP', 'STOP_LIMIT'].includes(order.order_type)) changes.stop_price = Number(modifyValues.stop_price)
    setMutationId(order.id)
    setModifyError('')
    try {
      const updatedOrder = await modifyOrder(order.id, changes)
      notify(`Order #${order.id} modified`)
      setModifyTarget(null)
      refresh()
      if (selected?.id === order.id) setSelected(updatedOrder)
    } catch (requestError) { setModifyError(requestError.message || 'Order could not be modified.') }
    finally { setMutationId(null) }
  }

  return <div className="page-stack">
    <div className="page-title-row"><div><span className="eyebrow">ORDER MANAGEMENT</span><h1>Orders</h1><p>Review order status, executions, and activity.</p></div><button className="secondary-button" onClick={refresh}>Refresh</button></div>
    {error && <div className="page-error" role="alert">{error} <button onClick={refresh}>Retry</button></div>}
    <section className="content-card">
      <div className="filter-tabs" role="tablist" aria-label="Filter orders">{filters.map(([value, label]) => <button key={value} role="tab" aria-selected={filter === value} className={filter === value ? 'active' : ''} onClick={() => setFilter(value)}>{label}{value === 'ALL' && <span>{orders.length}</span>}</button>)}</div>
      {loading ? <div className="loading-block">Loading orders…</div> : visible.length ? <DataTable><thead><tr><th>Order</th><th>Instrument</th><th>Side</th><th>Type</th><th>Order terms</th><th>Qty / Filled</th><th>Remaining</th><th>Average fill</th><th>Status</th><th>Placed</th><th>Actions</th></tr></thead><tbody>{visible.map((order) => <tr key={order.id}>
        <td className="order-id">#{order.id}</td><td><strong>{order.stock_symbol}</strong></td><td className={order.side === 'BUY' ? 'positive' : 'negative'}>{order.side}</td><td>{order.order_type}</td>
        <td className="order-terms">{order.limit_price != null && <span>Limit {formatCurrency(order.limit_price)}</span>}{order.stop_price != null && <span>Stop {formatCurrency(order.stop_price)}{order.stop_triggered ? ' · triggered' : ''}</span>}{order.limit_price == null && order.stop_price == null && '—'}</td>
        <td className="numeric">{formatQuantity(order.quantity)} / {formatQuantity(order.filled_quantity)}</td><td className="numeric">{formatQuantity(order.remaining_quantity)}</td><td className="numeric">{order.average_fill_price == null ? '—' : formatCurrency(order.average_fill_price)}</td><td><StatusBadge status={order.status}/></td><td>{formatDateTime(order.created_at)}</td>
        <td><div className="order-row-actions"><button className="mini-button" onClick={() => openOrder(order)}>Details</button>{cancellable(order.status) && <button className="mini-button danger-button" disabled={mutationId === order.id} onClick={() => setConfirmCancel(order)}>Cancel</button>}{modifiable(order) && <button className="mini-button" disabled={mutationId === order.id} onClick={() => startModify(order)}>Modify</button>}</div></td>
      </tr>)}</tbody></DataTable> : <EmptyState title={filter === 'ALL' ? 'No orders yet.' : `No ${filter.toLowerCase().replaceAll('_', ' ')} orders.`} detail="Your order activity will appear here."/>}
    </section>
    {selected && <Modal title={`Order #${selected.id}`} eyebrow="ORDER DETAILS" onClose={closeDetails} wide>
      <div className="order-detail-head"><div><strong>{selected.stock_symbol}</strong><span>{selected.side} {selected.order_type}</span></div><StatusBadge status={selected.status}/></div>
      <div className="detail-grid"><div><span>Quantity</span><strong>{formatQuantity(selected.quantity)}</strong></div><div><span>Filled</span><strong>{formatQuantity(selected.filled_quantity)}</strong></div><div><span>Remaining</span><strong>{formatQuantity(selected.remaining_quantity)}</strong></div><div><span>Average fill</span><strong>{selected.average_fill_price == null ? '—' : formatCurrency(selected.average_fill_price)}</strong></div><div><span>Limit price</span><strong>{selected.limit_price == null ? '—' : formatCurrency(selected.limit_price)}</strong></div><div><span>Stop price</span><strong>{selected.stop_price == null ? '—' : formatCurrency(selected.stop_price)}</strong></div><div><span>Stop triggered</span><strong>{selected.stop_triggered ? formatDateTime(selected.triggered_at) : 'No'}</strong></div><div><span>Created</span><strong>{formatDateTime(selected.created_at)}</strong></div></div>
      {detailLoading ? <div className="loading-block">Loading order activity…</div> : detailError ? <div className="page-error" role="alert">{detailError} <button onClick={() => loadDetails(selected)}>Retry</button></div> : <>
        <h3 className="subsection-title">Order event timeline</h3>{events.length ? <ol className="event-timeline">{events.map((event) => <li key={event.id}><i/><div><strong>{event.event_type.replaceAll('_', ' ')}</strong><span>{formatDateTime(event.created_at)}</span>{Object.keys(event.metadata_json || {}).length > 0 && <small>{Object.entries(event.metadata_json).map(([key, value]) => `${key.replaceAll('_', ' ')}: ${value}`).join(' · ')}</small>}</div></li>)}</ol> : <p className="muted-copy">No event records are available for this order.</p>}
        <h3 className="subsection-title">Execution history</h3>{executions.length ? <DataTable><thead><tr><th>Reference</th><th>Quantity</th><th>Price</th><th>Fees</th><th>Net cash effect</th><th>Time</th></tr></thead><tbody>{executions.map((fill) => <tr key={fill.id}><td>{fill.execution_ref}</td><td>{formatQuantity(fill.quantity)}</td><td>{formatCurrency(fill.execution_price)}</td><td>{fill.fees == null ? '—' : formatCurrency(fill.fees)}</td><td>{fill.net_cash_effect == null ? '—' : formatCurrency(fill.net_cash_effect)}</td><td>{formatDateTime(fill.executed_at)}</td></tr>)}</tbody></DataTable> : <p className="muted-copy">No executions recorded.</p>}
      </>}
      <div className="modal-actions">{cancellable(selected.status) && <button className="secondary-button danger-button" onClick={() => setConfirmCancel(selected)}>Cancel order</button>}{modifiable(selected) && <button className="secondary-button" onClick={() => startModify(selected)}>Modify order</button>}</div>
    </Modal>}
    {confirmCancel && <Modal title="Cancel order?" eyebrow="CONFIRM CANCELLATION" onClose={() => mutationId == null && setConfirmCancel(null)}><p>Cancel the remaining quantity of order #{confirmCancel.id} ({confirmCancel.stock_symbol})? Any remaining reserved funds or shares will be released.</p><div className="modal-actions"><button className="secondary-button" disabled={mutationId === confirmCancel.id} onClick={() => setConfirmCancel(null)}>Keep order</button><button className="primary-button danger-button" disabled={mutationId === confirmCancel.id} onClick={doCancel}>{mutationId === confirmCancel.id ? 'Cancelling…' : 'Confirm cancel'}</button></div></Modal>}
    {modifyTarget && <Modal title={`Modify order #${modifyTarget.id}`} eyebrow="ORDER AMENDMENT" onClose={() => mutationId == null && setModifyTarget(null)}><form className="modify-form" onSubmit={doModify}><label>Quantity<input type="number" min={modifyTarget.filled_quantity + 1} step="1" required value={modifyValues.quantity} onChange={(event) => setModifyValues({ ...modifyValues, quantity: event.target.value })}/></label>{['LIMIT', 'STOP_LIMIT'].includes(modifyTarget.order_type) && <label>Limit price<input type="number" min="0.01" step="0.01" required value={modifyValues.limit_price} onChange={(event) => setModifyValues({ ...modifyValues, limit_price: event.target.value })}/></label>}{['STOP', 'STOP_LIMIT'].includes(modifyTarget.order_type) && <label>Stop price<input type="number" min="0.01" step="0.01" required value={modifyValues.stop_price} onChange={(event) => setModifyValues({ ...modifyValues, stop_price: event.target.value })}/></label>}{modifyError && <p className="inline-error" role="alert">{modifyError}</p>}<p className="data-footnote">Available funds or shares are rechecked before changes are accepted.</p><div className="modal-actions"><button type="button" className="secondary-button" disabled={mutationId === modifyTarget.id} onClick={() => setModifyTarget(null)}>Back</button><button className="primary-button" disabled={mutationId === modifyTarget.id}>{mutationId === modifyTarget.id ? 'Saving…' : 'Confirm modification'}</button></div></form></Modal>}
  </div>
}
