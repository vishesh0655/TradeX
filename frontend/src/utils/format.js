const inr = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

export const formatCurrency = (value) => inr.format(Number(value) || 0)
export const formatPrice = formatCurrency
export const formatQuantity = (value) => new Intl.NumberFormat('en-IN').format(Number(value) || 0)
export const formatPercent = (value) => `${Number(value || 0) > 0 ? '+' : ''}${Number(value || 0).toFixed(2)}%`
export const formatDateTime = (value) => value
  ? new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
  : '—'
