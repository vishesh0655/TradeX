
import { useEffect, useRef, useState } from 'react'
import {
  RecaptchaVerifier,
  signInWithPhoneNumber,
} from 'firebase/auth'
import { auth } from './firebase'

function PhoneLogin({ onPhoneLogin, rememberMe }) {
  const [phone, setPhone] = useState('')
  const [otp, setOtp] = useState('')
  const [confirmation, setConfirmation] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const recaptchaRef = useRef(null)
  const verifierRef = useRef(null)

  useEffect(() => {
    return () => {
      if (verifierRef.current) {
        verifierRef.current.clear()
        verifierRef.current = null
      }
    }
  }, [])

  const sendOtp = async (e) => {
    e.preventDefault()
    setError('')
    setMessage('')

    const cleanedPhone = phone.replace(/\D/g, '')

    if (!/^[6-9]\d{9}$/.test(cleanedPhone)) {
      setError('Enter a valid 10-digit Indian mobile number.')
      return
    }

    setLoading(true)

    try {
      if (verifierRef.current) {
        verifierRef.current.clear()
      }

      verifierRef.current = new RecaptchaVerifier(
        auth,
        recaptchaRef.current,
        {
          size: 'normal',
          callback: () => {},
          'expired-callback': () => {
            setError('reCAPTCHA expired. Please try again.')
          },
        }
      )

      const confirmationResult = await signInWithPhoneNumber(
        auth,
        `+91${cleanedPhone}`,
        verifierRef.current
      )

      setConfirmation(confirmationResult)
      setMessage('OTP sent to your mobile number.')
    } catch (err) {
      console.error('Phone OTP error:', err)
      setError(err.message || 'Unable to send OTP.')
      if (verifierRef.current) {
        verifierRef.current.clear()
        verifierRef.current = null
      }
    } finally {
      setLoading(false)
    }
  }

  const verifyOtp = async (e) => {
    e.preventDefault()
    setError('')
    setMessage('')

    if (!confirmation) {
      setError('Please request an OTP first.')
      return
    }

    if (!/^\d{6}$/.test(otp)) {
      setError('Enter the 6-digit OTP.')
      return
    }

    setLoading(true)

    try {
      const result = await confirmation.confirm(otp)
      const firebaseIdToken = await result.user.getIdToken()

      await onPhoneLogin(firebaseIdToken, rememberMe)
    } catch (err) {
      console.error('OTP verification error:', err)
      setError(err.message || 'OTP verification failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="phone-login">
      {!confirmation ? (
        <form onSubmit={sendOtp}>
          <label htmlFor="phone">Mobile number</label>

          <div className="phone-input-row">
            <span>+91</span>
            <input
              id="phone"
              type="tel"
              inputMode="numeric"
              autoComplete="tel-national"
              placeholder="10-digit mobile number"
              value={phone}
              onChange={(e) =>
                setPhone(e.target.value.replace(/\D/g, '').slice(0, 10))
              }
              required
            />
          </div>

          <div ref={recaptchaRef} />

          <button type="submit" disabled={loading}>
            {loading ? 'Sending OTP...' : 'Send OTP'}
          </button>
        </form>
      ) : (
        <form onSubmit={verifyOtp}>
          <label htmlFor="otp">Enter 6-digit OTP</label>

          <input
            id="otp"
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder="Enter OTP"
            value={otp}
            onChange={(e) =>
              setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))
            }
            required
          />

          <button type="submit" disabled={loading}>
            {loading ? 'Verifying...' : 'Verify and Continue'}
          </button>

          <button
            type="button"
            disabled={loading}
            onClick={() => {
              setConfirmation(null)
              setOtp('')
              setError('')
              setMessage('')
            }}
          >
            Change phone number
          </button>
        </form>
      )}

      {message && <p className="auth-status">{message}</p>}
      {error && <p className="auth-status auth-error">{error}</p>}
    </div>
  )
}

export default PhoneLogin