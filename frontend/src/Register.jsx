import { useEffect, useRef, useState } from 'react'
import './Auth.css'

function Register({ onRegisterSuccess, onSwitchToLogin }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)

  const googleButtonRef = useRef(null)

  const handleGoogleResponse = async (response) => {
    setError('')
    setSuccess(false)
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
        throw new Error(data.detail || 'Google signup failed')
      }

      localStorage.setItem('token', data.access_token)

      if (onRegisterSuccess) {
        onRegisterSuccess()
      }
    } catch (err) {
      setError(err.message || 'Google signup failed')
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
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()

    setError('')
    setSuccess(false)
    setLoading(true)

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/register`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            name,
            email,
            password,
          }),
        }
      )

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || 'Registration failed')
      }

      setSuccess(true)
      setName('')
      setEmail('')
      setPassword('')

      if (onRegisterSuccess) {
        onRegisterSuccess()
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-scene">
        <div className="auth-glow auth-glow-one" />
        <div className="auth-glow auth-glow-two" />

        <div className="auth-ticker auth-ticker-top">
          <span><b>NIFTY 50</b> 24,812.35 <i className="up">▲0.42%</i></span>
          <span><b>SENSEX</b> 81,205.60 <i className="up">▲0.38%</i></span>
          <span><b>RELIANCE</b> 2,945.10 <i className="down">▼0.15%</i></span>
          <span><b>TCS</b> 4,102.75 <i className="up">▲0.61%</i></span>
          <span><b>INFY</b> 1,842.20 <i className="up">▲0.18%</i></span>

          <span><b>NIFTY 50</b> 24,812.35 <i className="up">▲0.42%</i></span>
          <span><b>SENSEX</b> 81,205.60 <i className="up">▲0.38%</i></span>
          <span><b>RELIANCE</b> 2,945.10 <i className="down">▼0.15%</i></span>
          <span><b>TCS</b> 4,102.75 <i className="up">▲0.61%</i></span>
          <span><b>INFY</b> 1,842.20 <i className="up">▲0.18%</i></span>
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
              Create your free paper trading account
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

            {success && (
              <div className="auth-status auth-success">
                Account created! You can now log in.
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