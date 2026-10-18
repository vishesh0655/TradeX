import { api } from './client'

const exchangeCredential = (provider, credential) => api(`/auth/${provider}`, {
  method: 'POST',
  anonymous: true,
  body: JSON.stringify({ credential }),
})

export const signInWithGoogle = (credential) => exchangeCredential('google', credential)
export const signInWithVerifiedEmail = (credential) => exchangeCredential('email', credential)
export const signInWithPhone = (credential) => exchangeCredential('phone', credential)

export const signInLegacy = (email, password) => api('/login', {
  method: 'POST',
  anonymous: true,
  body: JSON.stringify({ email, password }),
})
