import { api } from './client'

const queryString = (params) => {
  const query = new URLSearchParams()
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, value)
  })
  const encoded = query.toString()
  return encoded ? `?${encoded}` : ''
}

export const getOrders = (params = {}) => api(`/orders${queryString(params)}`)
export const getOrder = (id) => api(`/orders/${id}`)
export const getOrderEvents = (id, params = {}) => api(`/orders/${id}/events${queryString(params)}`)
export const getExecutions = (id, params = {}) => api(`/orders/${id}/executions${queryString(params)}`)

export const placeOrder = (order) => api('/orders', {
  method: 'POST',
  body: JSON.stringify(order),
})

export const cancelOrder = (id) => api(`/orders/${id}/cancel`, {
  method: 'POST',
})

export const modifyOrder = (id, changes) => api(`/orders/${id}`, {
  method: 'PATCH',
  body: JSON.stringify(changes),
})
