import { api } from './client'

export const getWallet = () => api('/wallet')
export const getWalletTransactions = () => api('/wallet/transactions')
