import { api } from './client'

export const getWatchlist = () => api('/watchlist')
export const addToWatchlist = (symbol) => api('/watchlist', {
  method: 'POST',
  body: JSON.stringify({ symbol }),
})
export const removeFromWatchlist = (symbol) => api(`/watchlist/${encodeURIComponent(symbol)}`, {
  method: 'DELETE',
})
