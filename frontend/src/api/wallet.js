import { api } from './client'

export const getWallet = () => api('/wallet')
export const getWalletTransactions = (params = {}) => {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, value)
  })
  const encoded = query.toString()
  return api(`/wallet/transactions${encoded ? `?${encoded}` : ''}`)
}
