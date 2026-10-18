const API_URL = import.meta.env.VITE_API_URL

export class ApiError extends Error {
  constructor(message, status = 0, code = 'REQUEST_FAILED') {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

export function getToken() {
  return localStorage.getItem('token') || sessionStorage.getItem('token')
}

export async function api(path, options = {}) {
  const { anonymous = false, ...requestOptions } = options
  const headers = new Headers(options.headers || {})
  const token = getToken()
  if (token && !anonymous) headers.set('Authorization', `Bearer ${token}`)
  if (requestOptions.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let response
  try {
    response = await fetch(`${API_URL}${path}`, { ...requestOptions, headers })
  } catch {
    throw new ApiError('Unable to reach TradeX. Check that the local API is running.', 0, 'NETWORK_ERROR')
  }

  const data = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) {
    const detail = data?.detail
    const message = typeof detail === 'string'
      ? detail
      : detail?.[0]?.msg || `Request failed (${response.status})`
    if (response.status === 401) {
      localStorage.removeItem('token')
      sessionStorage.removeItem('token')
      window.dispatchEvent(new Event('tradex:unauthorized'))
    }
    throw new ApiError(message, response.status, detail?.code || 'REQUEST_FAILED')
  }
  return data
}
