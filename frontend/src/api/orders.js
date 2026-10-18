import { api } from './client'

export const getOrders = () => api('/orders')
export const getOrderEvents = (id) => api(`/orders/${id}/events`)
export const getExecutions = (id) => api(`/orders/${id}/executions`)

export const placeOrder = (order) => api('/orders', {
  method: 'POST',
  body: JSON.stringify(order),
})
