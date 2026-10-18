import { useCallback, useEffect, useRef, useState } from 'react'
import {
  createUserWithEmailAndPassword,
  sendEmailVerification,
  updateProfile,
  reload,
  getIdToken,
} from 'firebase/auth'
import { auth } from './firebase'
import { signInWithGoogle, signInWithVerifiedEmail } from './api/auth'
import './Auth.css'

function Register({ onRegisterSuccess, onSwitchToLogin, onSwitchToPhone, isActive = true }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [verificationSent, setVerificationSent] = useState(false)

  const googleButtonRef = useRef(null)

  const handleGoogleResponse = useCallback(async (response) => {
    setError('')
    setGoogleLoading(true)

    try {
      const data = await signInWithGoogle(response.credential)

      localStorage.setItem('token', data.access_token)

      if (onRegisterSuccess) {
        onRegisterSuccess()
      }
    } catch (err) {
      setError(err.message || 'Google signup failed')
    } finally {
      setGoogleLoading(false)
    }
  }, [onRegisterSuccess])

  useEffect(() => {
    if (!isActive) return undefined

    const initializeGoogle = () => {
      const googleIdentity = window.google
      if (!googleIdentity || !googleButtonRef.current) {
        return
      }

      googleIdentity.accounts.id.initialize({
        client_id: import.meta.env.VITE_GOOGLE_CLIENT_ID,
        callback: handleGoogleResponse,
      })

      googleButtonRef.current.innerHTML = ''

      googleIdentity.accounts.id.renderButton(
        googleButtonRef.current,
        {
          theme: 'outline',
          size: 'large',
          width: 180,
          text: 'signup_with',
          shape: 'rectangular',
          logo_alignment: 'left',
        }
      )
    }

    if (window.google) {
      initializeGoogle()
      return
    }

    const existingScript = document.querySelector(
      'script[src="https://accounts.google.com/gsi/client"]'
    )

    if (existingScript) {
      existingScript.addEventListener('load', initializeGoogle)

      return () => {
        existingScript.removeEventListener('load', initializeGoogle)
      }
    }

    const script = document.createElement('script')

    script.src = 'https://accounts.google.com/gsi/client'
    script.async = true
    script.defer = true
    script.onload = initializeGoogle

    document.head.appendChild(script)

    return () => {
      script.onload = null
    }
  }, [handleGoogleResponse, isActive])

  const handleSubmit = async (e) => {
  e.preventDefault()

  setError('')
  setLoading(true)

  try {
    const userCredential = await createUserWithEmailAndPassword(
      auth,
      email.trim(),
      password
    )

    await updateProfile(userCredential.user, {
      displayName: name.trim(),
    })

    await sendEmailVerification(userCredential.user, {
      url: window.location.origin,
      handleCodeInApp: false,
    })

    setVerificationSent(true)
    setPassword('')
  } catch (err) {
    const messages = {
      'auth/email-already-in-use': 'This email is already registered. Please sign in.',
      'auth/invalid-email': 'Please enter a valid email address.',
      'auth/weak-password': 'Password must be at least 6 characters.',
      'auth/too-many-requests': 'Too many attempts. Please try again later.',
    }

    setError(messages[err.code] || err.message || 'Registration failed')
  } finally {
    setLoading(false)
  }
}

  const handleConfirmVerification = async () => {
    setError('')
    setLoading(true)

    try {
      const user = auth.currentUser

      if (!user) {
        throw new Error(
          'Your signup session has expired. Please sign up again.'
        )
      }

      // Refresh Firebase user status after email verification
      await reload(user)

      if (!user.emailVerified) {
        setError(
          'Email not verified yet. Please verify your email first, then try again.'
        )
        return
      }

      // Get a fresh Firebase ID token
      const firebaseToken = await getIdToken(user, true)

      // Send verified identity to TradeX backend
      const data = await signInWithVerifiedEmail(firebaseToken)

      // Save TradeX JWT
      localStorage.setItem('token', data.access_token)

      // Continue to the app
      if (onRegisterSuccess) {
        onRegisterSuccess()
      }
    } catch (err) {
      setError(
        err.message || 'Email verification failed. Please try again.'
      )
    } finally {
      setLoading(false)
    }
  }

  const handleResendVerification = async () => {
    setError('')
    setLoading(true)

    try {
      const user = auth.currentUser

      if (!user) {
        throw new Error(
          'Signup session expired. Please sign up again.'
        )
      }

      await reload(user)

      if (user.emailVerified) {
        setError(
          'Your email is already verified. Click the verification button to continue.'
        )
        return
      }

      await sendEmailVerification(user, {
        url: window.location.origin,
        handleCodeInApp: false,
      })

      setVerificationSent(true)
    } catch (err) {
      setError(
        err.message || 'Could not resend the verification email.'
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-page auth-screen auth-screen-register" aria-hidden={!isActive} inert={!isActive}>
      <div className="auth-scene">
        <div className="auth-glow auth-glow-one" />
        <div className="auth-glow auth-glow-two" />

        <div className="auth-ticker auth-ticker-top">
          {['MARKET OVERVIEW', 'PORTFOLIO TOOLS', 'ORDER MANAGEMENT', 'WATCHLIST', 'TRADEX',
            'MARKET OVERVIEW', 'PORTFOLIO TOOLS', 'ORDER MANAGEMENT', 'WATCHLIST', 'TRADEX'].map((label, index) => (
            <span key={`${label}-${index}`}><b>{label}</b></span>
          ))}
        </div>
      </div>

      <div className="auth-card">
        <div className="auth-form-panel">
          <form onSubmit={handleSubmit} className="auth-form">
            <div className="auth-logo">
              <div className="auth-logo-inner">
                <svg viewBox="0 0 24 24" fill="none">
                  <path
                    d="M3 16.5L9 10.5L13 13.5L20 5.5"
                    stroke="url(#registerGradient)"
                    strokeWidth="2.3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <path
                    d="M14.5 5.5H20V11"
                    stroke="url(#registerGradient)"
                    strokeWidth="2.3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <defs>
                    <linearGradient
                      id="registerGradient"
                      x1="3"
                      y1="16"
                      x2="20"
                      y2="5"
                    >
                      <stop stopColor="#0e9f86" />
                      <stop offset="1" stopColor="#3b6fe0" />
                    </linearGradient>
                  </defs>
                </svg>
              </div>
            </div>

            <h1 className="auth-title">Get started</h1>

            <p className="auth-subtitle">
              Create your TradeX account
            </p>

            <div className="auth-input-group">
              <span className="auth-input-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
              </span>

              <input
                type="text"
                placeholder=" "
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="name"
                required
              />

              <label>Full name</label>
            </div>

            <div className="auth-input-group">
              <span className="auth-input-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path d="M22 6 12 13 2 6" />
                  <path d="M2 6h20v12H2z" />
                </svg>
              </span>

              <input
                type="email"
                placeholder=" "
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
              />

              <label>Email address</label>
            </div>

            <div className="auth-input-group">
              <span className="auth-input-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <rect x="4" y="10" width="16" height="10" rx="2" />
                  <path d="M8 10V7a4 4 0 0 1 8 0v3" />
                </svg>
              </span>

              <input
                type={showPassword ? 'text' : 'password'}
                placeholder=" "
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                required
              />

              <label>Password</label>

              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? '🙈' : '👁'}
              </button>
            </div>

            {error && (
              <div className="auth-status auth-error">
                {error}
              </div>
            )}

            {verificationSent && (
              <div className="auth-status auth-success">
                <p>
                  Verification email sent to {email}.
                  Please check your inbox and spam folder.
                </p>

                <button
                  type="button"
                  className="auth-button"
                  onClick={handleConfirmVerification}
                  disabled={loading || googleLoading}
                >
                  {loading ? (
                    <span className="auth-spinner" />
                  ) : (
                    "I've verified my email"
                  )}
                </button>

                <button
                  type="button"
                  className="auth-link"
                  onClick={handleResendVerification}
                  disabled={loading || googleLoading}
                >
                  Resend verification email
                </button>
              </div>
            )}

            <button
              type="submit"
              className={`auth-button ${loading ? 'loading' : ''}`}
              disabled={loading || googleLoading}
            >
              {loading ? (
                <span className="auth-spinner" />
              ) : (
                'Create account'
              )}
            </button>

            <div className="trust-row">
              <span>
                <i /> Portfolio tools
              </span>
              <span>
                <i /> Order management
              </span>
              <span>
                <i /> Market overview
              </span>
            </div>

            <div className="auth-divider">
              <span>or sign up with</span>
            </div>

            <div className="social-row">
              <div
                ref={googleButtonRef}
                className="google-login-button"
              />

              <button
                type="button"
                className="social-button"
                onClick={onSwitchToPhone}
              >
                Continue with phone
              </button>

              <button
                type="button"
                className="social-button"
                disabled
                title="Apple Sign In coming soon"
              >
                Apple
              </button>
            </div>

            {googleLoading && (
              <div className="auth-status">
                Creating your TradeX account with Google...
              </div>
            )}

            <div className="mobile-switch">
              Already have an account?{' '}
              <button
                type="button"
                className="auth-link"
                onClick={onSwitchToLogin}
              >
                Sign in
              </button>
            </div>
          </form>
        </div>

        <div className="auth-overlay">
          <div className="feature-strip">
            <span>MARKET TOOLS</span>
            <span>PORTFOLIO TRACKING</span>
          </div>

          <div className="floating-orb orb-one" />
          <div className="floating-orb orb-two" />

          <div className="market-mini">
            <div className="market-top">
              <span>ACCOUNT OVERVIEW</span>
              <span className="preview-pill">PORTFOLIO</span>
            </div>
            <div className="auth-preview-copy">Holdings, balances, and orders<br />in one place</div>
            <div className="market-bottom">
              <span>Account balance</span>
              <span>Portfolio</span>
            </div>
          </div>

          <div className="overlay-content">
            <span className="overlay-brand">TRADEX</span>

            <h2>Already trading with us?</h2>

            <p>
              Sign in to check your portfolio and pick up
              where you left off.
            </p>

            <button
              type="button"
              className="overlay-button"
              onClick={onSwitchToLogin}
            >
              Sign in
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Register
