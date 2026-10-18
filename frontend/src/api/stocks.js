import { api } from './client'

export async function getStocks(params = {}) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, value)
  })
  const encoded = query.toString()
  const data = await api(`/stocks${encoded ? `?${encoded}` : ''}`)
  return data.stocks || []
}

export function getQuote(symbol) {
  return api(`/stocks/${encodeURIComponent(symbol)}/quote`)
}
