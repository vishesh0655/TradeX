import { api } from './client'

export const getProfile = () => api('/me')
export const getHoldings = () => api('/holdings')
