import { api } from './client'

export const estimateOrderFees = (estimate) => api('/fees/estimate', {
  method: 'POST',
  body: JSON.stringify(estimate),
})
