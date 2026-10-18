import { DataTable, EmptyState, MetricCard, StatusBadge } from '../components/common/ui'
import { formatCurrency, formatDateTime } from '../utils/format'

export default function WalletPage({ wallet, transactions, loading, retry, error }) {
  const cashBalance = Number(wallet?.cash_balance ?? wallet?.balance ?? 0)
  const reservedCash = Number(wallet?.reserved_cash || 0)
  const availableCash = Number(wallet?.available_cash ?? cashBalance - reservedCash)

  return <div className="page-stack">
    <div className="page-title-row">
      <div>
        <span className="eyebrow">ACCOUNT BALANCE</span>
        <h1>Balance</h1>
        <p>Review available funds, reservations, and transactions.</p>
      </div>
    </div>
    {error && <div className="page-error" role="alert">{error} <button onClick={retry}>Retry</button></div>}
    <div className="metric-grid metric-grid-three">
      <MetricCard label="Balance" value={formatCurrency(cashBalance)} note="TradeX account funds" />
      <MetricCard label="Reserved funds" value={formatCurrency(reservedCash)} note="Held for open orders" />
      <MetricCard label="Available funds" value={formatCurrency(availableCash)} note="Available for new orders" />
    </div>
    <section className="content-card">
      <div className="section-heading">
        <div><span className="eyebrow">ACCOUNT LEDGER</span><h2>Transaction history</h2></div>
        <span className="row-count">{transactions.length} entries</span>
      </div>
      {loading ? <div className="loading-block">Loading transactions…</div> : transactions.length ? <DataTable>
        <thead><tr><th>Type</th><th>Reference</th><th>Amount</th><th>Balance after</th><th>Details</th><th>Time</th></tr></thead>
        <tbody>{transactions.map((item) => {
          const metadata = item.metadata_json || {}
          const isFee = item.transaction_type === 'TRADING_FEE'
          const detail = isFee
            ? `Configured fee${metadata.brokerage != null ? ` · brokerage ${formatCurrency(metadata.brokerage)}` : ''}${metadata.platform != null ? ` · platform ${formatCurrency(metadata.platform)}` : ''}${metadata.taxes != null ? ` · taxes ${formatCurrency(metadata.taxes)}` : ''}`
            : item.transaction_type.includes('RESERVATION')
              ? 'Funds reservation'
              : metadata.reason || metadata.description || 'Account entry'

          return <tr key={item.id}>
            <td><StatusBadge status={item.transaction_type} /></td>
            <td>{item.reference_id ? `Order #${item.reference_id}` : '—'}</td>
            <td className={`numeric ${item.amount >= 0 ? 'positive' : 'negative'}`}>{item.amount > 0 ? '+' : ''}{formatCurrency(item.amount)}</td>
            <td className="numeric">{formatCurrency(item.balance_after)}</td>
            <td className={isFee ? 'fee-ledger-detail' : ''}>{detail}</td>
            <td>{formatDateTime(item.created_at)}</td>
          </tr>
        })}</tbody>
      </DataTable> : <EmptyState title="No transactions yet." detail="Account activity, reservations, fills, and fees will appear here." />}
    </section>
    <p className="data-footnote">Funds are internal TradeX account credits. They cannot be deposited or withdrawn.</p>
  </div>
}
