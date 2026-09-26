import { useEffect, useRef, useState } from 'react'
import {
  signInWithEmailAndPassword,
  sendEmailVerification,
  sendPasswordResetEmail,
  reload,
  getIdToken,
} from 'firebase/auth'
import { auth } from './firebase'
import './Auth.css'
function Login({ onLoginSuccess, onSwitchToRegister, onSwitchToPhone }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [rememberMe, setRememberMe] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [verificationUser, setVerificationUser] = useState(null)
  const [resetLoading, setResetLoading] = useState(false)
const [resetMessage, setResetMessage] = useState('')

  const googleButtonRef = useRef(null)
  const rememberMeRef = useRef(rememberMe)
rememberMeRef.current = rememberMe
  const saveAuthToken = (token) => {
  if (rememberMeRef.current) {
    localStorage.setItem('token', token)
    sessionStorage.removeItem('token')
  } else {
    sessionStorage.setItem('token', token)
    localStorage.removeItem('token')
  }
}

  const handleGoogleResponse = async (response) => {
    setError('')
    setGoogleLoading(true)

    try {
      const result = await fetch(
        `${import.meta.env.VITE_API_URL}/auth/google`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            credential: response.credential,
          }),
        }
      )

      const data = await result.json()

      if (!result.ok) {
        throw new Error(data.detail || 'Google login failed')
      }

      saveAuthToken(data.access_token)

      onLoginSuccess()
    } catch (err) {
      setError(err.message || 'Google login failed')
    } finally {
      setGoogleLoading(false)
    }
  }

  useEffect(() => {
    const initializeGoogle = () => {
      if (!window.google || !googleButtonRef.current) {
        return
      }

      google.accounts.id.initialize({
        client_id: import.meta.env.VITE_GOOGLE_CLIENT_ID,
        callback: handleGoogleResponse,
      })

      googleButtonRef.current.innerHTML = ''

      google.accounts.id.renderButton(
        googleButtonRef.current,
        {
          theme: 'outline',
          size: 'large',
          width: 180,
          text: 'continue_with',
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
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setVerificationUser(null)
    setLoading(true)

    try {
      // Sign in through Firebase Authentication
      const userCredential = await signInWithEmailAndPassword(
        auth,
        email.trim(),
        password
      )

      const user = userCredential.user

      // Refresh Firebase user status
      await reload(user)

      if (!user.emailVerified) {
        setVerificationUser(user)
        setError(
          'Your email is not verified yet. Check your inbox, verify your email, then click the button below.'
        )
        return
      }

      // Get a fresh Firebase ID token
      const firebaseToken = await getIdToken(user, true)

      // Exchange Firebase identity for a TradeX JWT
      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/auth/email`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            credential: firebaseToken,
          }),
        }
      )

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || 'TradeX login failed')
      }

      // Respect Remember Me
      saveAuthToken(data.access_token)

      if (onLoginSuccess) {
        onLoginSuccess()
      }
    } catch (err) {
      // If Firebase doesn't recognize this login, try the legacy
      // PostgreSQL-backed TradeX login for accounts created before Firebase.
      const shouldTryLegacyLogin = [
        'auth/invalid-credential',
        'auth/user-not-found',
        'auth/wrong-password',
      ].includes(err.code)

      if (shouldTryLegacyLogin) {
        try {
          const legacyResponse = await fetch(
            `${import.meta.env.VITE_API_URL}/login`,
            {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({
                email: email.trim(),
                password,
              }),
            }
          )

          const legacyData = await legacyResponse.json()

          if (legacyResponse.ok) {
            saveAuthToken(legacyData.access_token)

            if (onLoginSuccess) {
              onLoginSuccess()
            }
            return
          }

          // Prefer the legacy API's error when it also rejects the credentials.
          setError(
            legacyData.detail ||
              'Incorrect email or password. If this is a newer account, use your Firebase password.'
          )
        } catch (legacyErr) {
          setError(
            legacyErr.message ||
              'Could not connect to TradeX. Check your internet connection and try again.'
          )
        }
      } else {
        const messages = {
          'auth/invalid-credential': 'Incorrect email or password.',
          'auth/user-not-found': 'No account found with this email.',
          'auth/wrong-password': 'Incorrect email or password.',
          'auth/invalid-email': 'Please enter a valid email address.',
          'auth/user-disabled': 'This account has been disabled.',
          'auth/too-many-requests': 'Too many attempts. Please try again later.',
          'auth/network-request-failed': 'Network error. Check your internet connection.',
        }

        setError(messages[err.code] || err.message || 'Login failed')
      }
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
          'Your sign-in session has expired. Please sign in again.'
        )
      }

      await reload(user)

      if (user.emailVerified) {
        setVerificationUser(null)
        setError(
          'Your email is verified now. Click Continue to TradeX to sign in.'
        )
        return
      }

      await sendEmailVerification(user, {
        url: window.location.origin,
        handleCodeInApp: false,
      })

      setError('A new verification email has been sent. Check your inbox and spam folder.')
    } catch (err) {
      setError(err.message || 'Could not resend the verification email.')
    } finally {
      setLoading(false)
    }
  }

  const handleContinueAfterVerification = async () => {
    setError('')
    setLoading(true)

    try {
      const user = auth.currentUser

      if (!user) {
        throw new Error('Please sign in again to continue.')
      }

      await reload(user)

      if (!user.emailVerified) {
        setError('Your email is still not verified. Please check your inbox.')
        return
      }

      const firebaseToken = await getIdToken(user, true)

      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/auth/email`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            credential: firebaseToken,
          }),
        }
      )

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || 'TradeX login failed')
      }

      saveAuthToken(data.access_token)

      if (onLoginSuccess) {
        onLoginSuccess()
      }
    } catch (err) {
      setError(err.message || 'Could not complete login.')
    } finally {
      setLoading(false)
    }
  }
  const handleForgotPassword = async () => {
  setError('')
  setResetMessage('')

  const userEmail = email.trim()

  if (!userEmail) {
    setError('Please enter your email address first.')
    return
  }

  setResetLoading(true)

  try {
    await sendPasswordResetEmail(auth, userEmail)

    setResetMessage(
      'If an account exists for this email, a password reset link has been sent. Check your inbox and spam folder.'
    )
  } catch (err) {
    const messages = {
      'auth/invalid-email': 'Please enter a valid email address.',
      'auth/too-many-requests':
        'Too many attempts. Please try again later.',
      'auth/network-request-failed':
        'Network error. Check your internet connection.',
    }

    setError(
      messages[err.code] ||
      'Could not send the reset email. Please try again.'
    )
  } finally {
    setResetLoading(false)
  }
}

  return (
    <div className="auth-page">
      <div className="auth-scene">
        <div className="auth-glow auth-glow-one" />
        <div className="auth-glow auth-glow-two" />

        <div className="auth-ticker auth-ticker-top">
          <span>
            <b>NIFTY 50</b> 24,812.35 <i className="up">▲0.42%</i>
          </span>
          <span>
            <b>SENSEX</b> 81,205.60 <i className="up">▲0.38%</i>
          </span>
          <span>
            <b>RELIANCE</b> 2,945.10 <i className="down">▼0.15%</i>
          </span>
          <span>
            <b>TCS</b> 4,102.75 <i className="up">▲0.61%</i>
          </span>
          <span>
            <b>INFY</b> 1,842.20 <i className="up">▲0.18%</i>
          </span>

          <span>
            <b>NIFTY 50</b> 24,812.35 <i className="up">▲0.42%</i>
          </span>
          <span>
            <b>SENSEX</b> 81,205.60 <i className="up">▲0.38%</i>
          </span>
          <span>
            <b>RELIANCE</b> 2,945.10 <i className="down">▼0.15%</i>
          </span>
          <span>
            <b>TCS</b> 4,102.75 <i className="up">▲0.61%</i>
          </span>
          <span>
            <b>INFY</b> 1,842.20 <i className="up">▲0.18%</i>
          </span>
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
                    stroke="url(#loginGradient)"
                    strokeWidth="2.3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <path
                    d="M14.5 5.5H20V11"
                    stroke="url(#loginGradient)"
                    strokeWidth="2.3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <defs>
                    <linearGradient
                      id="loginGradient"
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

            <h1 className="auth-title">Welcome back</h1>

            <p className="auth-subtitle">
              Sign in to your TradeX account
            </p>

            <div className="auth-input-group">
              <span className="auth-input-icon">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                >
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
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                >
                  <rect x="4" y="10" width="16" height="10" rx="2" />
                  <path d="M8 10V7a4 4 0 0 1 8 0v3" />
                </svg>
              </span>

              <input
                type={showPassword ? 'text' : 'password'}
                placeholder=" "
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />

              <label>Password</label>

              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={
                  showPassword ? 'Hide password' : 'Show password'
                }
              >
                {showPassword ? '🙈' : '👁'}
              </button>
            </div>

            <div className="auth-options">
              <label className="remember-box">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                />
                <span className="custom-checkbox" />
                Remember me
              </label>

              <button
                type="button"
                className="auth-link"
                onClick={handleForgotPassword}
                disabled={loading || googleLoading || resetLoading}
              >
                {resetLoading ? 'Sending...' : 'Forgot password?'}
              </button>
            </div>

            {resetMessage && (
              <div className="auth-status auth-success">
                {resetMessage}
              </div>
            )}

            {error && (
              <div className="auth-status auth-error">
                {error}
              </div>
            )}

            {verificationUser && (
              <div className="auth-status auth-success">
                <button
                  type="button"
                  className="auth-button"
                  onClick={handleContinueAfterVerification}
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
                'Continue to TradeX'
              )}
            </button>

            <div className="trust-row">
              <span>
                <i /> Virtual funds
              </span>

              <span>
                <i /> Paper trading
              </span>

              <span>
                <i /> Built for practice
              </span>
            </div>

            <div className="auth-divider">
              <span>or continue with</span>
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
            </div>

            {googleLoading && (
              <div className="auth-status">
                Signing in with Google...
              </div>
            )}

            <div className="mobile-switch">
              New here?{' '}
              <button
                type="button"
                className="auth-link"
                onClick={onSwitchToRegister}
              >
                Create account
              </button>
            </div>
          </form>
        </div>

        <div className="auth-overlay">
          <div className="feature-strip">
            <span>PAPER TRADING</span>
            <span>LIVE UI</span>
          </div>

          <div className="floating-orb orb-one" />
          <div className="floating-orb orb-two" />

          <div className="market-mini">
            <div className="market-top">
              <span>NIFTY 50 · DEMO</span>

              <span className="live-pill">
                <i /> MARKET PULSE
              </span>
            </div>

            <svg className="spark-chart" viewBox="0 0 250 48">
              <path
                className="spark-area"
                d="M0 40 L18 34 L34 37 L52 27 L70 31 L89 20 L108 25 L127 14 L145 21 L164 12 L182 17 L202 7 L221 13 L250 3 L250 48 L0 48 Z"
              />

              <path
                d="M0 40 L18 34 L34 37 L52 27 L70 31 L89 20 L108 25 L127 14 L145 21 L164 12 L182 17 L202 7 L221 13 L250 3"
              />
            </svg>

            <div className="market-bottom">
              <span>Virtual portfolio</span>
              <span>+0.42%</span>
            </div>
          </div>

          <div className="overlay-content">
            <span className="overlay-brand">TRADEX</span>

            <h2>New to TradeX?</h2>

            <p>
              Create a free account and start paper trading
              with a virtual portfolio.
            </p>

            <button
              type="button"
              className="overlay-button"
              onClick={onSwitchToRegister}
            >
              Sign up
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Login