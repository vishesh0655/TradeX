import { useState } from 'react'
import PhoneLogin from './PhoneLogin'
import './Auth.css'

function PhoneLoginPage({ onPhoneLogin, onBack }) {
  const [rememberMe, setRememberMe] = useState(false)

  return (
    <div className="auth-page phone-auth-page">
      <div className="auth-card phone-auth-card">
        <div className="auth-form-panel phone-auth-panel">
          <div className="auth-form phone-auth-form">

            <h1 className="auth-title">
              Phone Login
            </h1>

            <p className="auth-subtitle">
              Sign in to TradeX using your mobile number
            </p>

            <PhoneLogin
              onPhoneLogin={onPhoneLogin}
              rememberMe={rememberMe}
            />

            <div className="phone-auth-options">
              <label className="remember-box">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) =>
                    setRememberMe(e.target.checked)
                  }
                />
                <span className="custom-checkbox" />
                Remember me
              </label>
            </div>

            <button
              type="button"
              className="auth-link phone-auth-back"
              onClick={onBack}
            >
              ← Back to login
            </button>

          </div>
        </div>
      </div>
    </div>
  )
}

export default PhoneLoginPage