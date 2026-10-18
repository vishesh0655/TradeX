import { api } from './client'

export async function getStocks() {
  const data = await api('/stocks')
  return data.stocks || []
}

export function getQuote(symbol) {
  return api(`/stocks/${encodeURIComponent(symbol)}/quote`)
}
