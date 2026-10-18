import { useEffect, useRef, useState } from 'react'
import {
  RecaptchaVerifier,
  signInWithPhoneNumber,
} from 'firebase/auth'
import { auth } from './firebase'

function PhoneLogin({ onPhoneLogin, rememberMe }) {
  const [phone, setPhone] = useState('')
  const [otp, setOtp] = useState(['', '', '', '', '', ''])
  const [confirmation, setConfirmation] = useState(null)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const [otpState, setOtpState] = useState('idle')
  const [resendTimer, setResendTimer] = useState(0)

  const recaptchaRef = useRef(null)
  const verifierRef = useRef(null)
  const otpRefs = useRef([])

  // --------------------------------------------------
  // CLEANUP
  // --------------------------------------------------

  useEffect(() => {
    return () => {
      if (verifierRef.current) {
        verifierRef.current.clear()
        verifierRef.current = null
      }
    }
  }, [])

  // --------------------------------------------------
  // RESEND COUNTDOWN
  // --------------------------------------------------

  useEffect(() => {
    if (resendTimer <= 0) return

    const timer = setInterval(() => {
      setResendTimer((prev) => {
        if (prev <= 1) {
          clearInterval(timer)
          return 0
        }

        return prev - 1
      })
    }, 1000)

    return () => clearInterval(timer)
  }, [resendTimer])

  // --------------------------------------------------
  // SEND OTP
  // --------------------------------------------------

  const sendOtp = async (e) => {
    if (e) e.preventDefault()

    setError('')
    setMessage('')
    setOtpState('idle')

    const cleanedPhone = phone.replace(/\D/g, '')

    if (!/^[6-9]\d{9}$/.test(cleanedPhone)) {
      setError('Enter a valid 10-digit Indian mobile number.')
      return
    }

    setLoading(true)

    try {
      if (verifierRef.current) {
        verifierRef.current.clear()
        verifierRef.current = null
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

      setOtp(['', '', '', '', '', ''])

      setMessage('Verification code sent to your phone.')

      setResendTimer(30)

      // Focus first OTP box
      setTimeout(() => {
        otpRefs.current[0]?.focus()
      }, 150)
    } catch (err) {
      console.error('Phone OTP error:', err)

      setError(
        err.message || 'Unable to send OTP. Please try again.'
      )

      if (verifierRef.current) {
        verifierRef.current.clear()
        verifierRef.current = null
      }
    } finally {
      setLoading(false)
    }
  }

  // --------------------------------------------------
  // OTP INPUT
  // --------------------------------------------------

  const handleOtpChange = (index, value) => {
    // Remove anything except numbers
    const digits = value.replace(/\D/g, '')

    if (!digits) {
      const updated = [...otp]
      updated[index] = ''
      setOtp(updated)
      return
    }

    // Handle paste / multiple digits
    if (digits.length > 1) {
      const updated = [...otp]

      digits
        .slice(0, 6)
        .split('')
        .forEach((digit, i) => {
          if (index + i < 6) {
            updated[index + i] = digit
          }
        })

      setOtp(updated)

      const nextIndex = Math.min(index + digits.length, 5)

      setTimeout(() => {
        otpRefs.current[nextIndex]?.focus()
      }, 0)

      return
    }

    // Normal single digit
    const updated = [...otp]
    updated[index] = digits[0]

    setOtp(updated)
    setOtpState('idle')
    setError('')

    // Move to next box
    if (index < 5) {
      setTimeout(() => {
        otpRefs.current[index + 1]?.focus()
      }, 0)
    }
  }

  // --------------------------------------------------
  // OTP KEYBOARD
  // --------------------------------------------------

  const handleOtpKeyDown = (index, e) => {
    if (e.key === 'Backspace') {
      if (otp[index]) {
        const updated = [...otp]
        updated[index] = ''
        setOtp(updated)
        return
      }

      if (index > 0) {
        const updated = [...otp]
        updated[index - 1] = ''
        setOtp(updated)

        otpRefs.current[index - 1]?.focus()
      }
    }

    if (e.key === 'ArrowLeft' && index > 0) {
      otpRefs.current[index - 1]?.focus()
    }

    if (e.key === 'ArrowRight' && index < 5) {
      otpRefs.current[index + 1]?.focus()
    }
  }

  // --------------------------------------------------
  // OTP PASTE
  // --------------------------------------------------

  const handleOtpPaste = (e) => {
    e.preventDefault()

    const pasted = e.clipboardData
      .getData('text')
      .replace(/\D/g, '')
      .slice(0, 6)

    if (!pasted) return

    const updated = ['', '', '', '', '', '']

    pasted.split('').forEach((digit, index) => {
      updated[index] = digit
    })

    setOtp(updated)
    setError('')
    setOtpState('idle')

    const focusIndex = Math.min(pasted.length, 5)

    setTimeout(() => {
      otpRefs.current[focusIndex]?.focus()
    }, 0)
  }

  // --------------------------------------------------
  // VERIFY OTP
  // --------------------------------------------------

  const verifyOtp = async (e) => {
    e.preventDefault()

    setError('')
    setMessage('')

    const enteredOtp = otp.join('')

    if (!confirmation) {
      setError('Please request an OTP first.')
      return
    }

    if (!/^\d{6}$/.test(enteredOtp)) {
      setError('Enter the complete 6-digit OTP.')
      setOtpState('bad')
      return
    }

    setLoading(true)
    setOtpState('verifying')

    try {
      const result = await confirmation.confirm(enteredOtp)

      const firebaseIdToken =
        await result.user.getIdToken()

      // Show success animation first
      setOtpState('success')
      setMessage('Phone number verified.')

      // Give animation time to play
      await new Promise((resolve) =>
        setTimeout(resolve, 900)
      )

      await onPhoneLogin(
        firebaseIdToken,
        rememberMe
      )
    } catch (err) {
      console.error('OTP verification error:', err)

      setOtpState('bad')

      if (
        err?.code === 'auth/invalid-verification-code'
      ) {
        setError('Incorrect OTP. Please try again.')
      } else if (
        err?.code === 'auth/code-expired'
      ) {
        setError(
          'This OTP has expired. Please request a new one.'
        )
      } else {
        setError(
          err.message ||
            'OTP verification failed. Please try again.'
        )
      }

      // Stop shake animation after it finishes
      setTimeout(() => {
        setOtpState('idle')
      }, 650)
    } finally {
      setLoading(false)
    }
  }

  // --------------------------------------------------
  // RESEND OTP
  // --------------------------------------------------

  const resendOtp = async () => {
    if (resendTimer > 0 || loading) return

    await sendOtp()
  }

  // --------------------------------------------------
  // CHANGE PHONE NUMBER
  // --------------------------------------------------

  const changePhone = () => {
    setConfirmation(null)

    setOtp([
      '',
      '',
      '',
      '',
      '',
      '',
    ])

    setError('')
    setMessage('')
    setOtpState('idle')
    setResendTimer(0)

    setTimeout(() => {
      document
        .getElementById('phone')
        ?.focus()
    }, 100)
  }

  // --------------------------------------------------
  // RENDER
  // --------------------------------------------------

  return (
    <div className="phone-login otp-v3">

      {/* ============================================
          PHONE NUMBER SCREEN
      ============================================ */}

      {!confirmation && (
        <div className="otp-v3-screen phone-number-screen">

          <div className="otp-v3-orbit">
            <div className="otp-v3-orbit-ring ring-one" />
            <div className="otp-v3-orbit-ring ring-two" />

            <div className="otp-v3-phone-icon">
              <span>⌕</span>
            </div>
          </div>

          <div className="otp-v3-heading">
            <h2>Verify your phone</h2>

            <p>
              We'll send a verification code
              to your mobile number
            </p>
          </div>

          <form onSubmit={sendOtp}>

            <div className="otp-v3-phone-field">

              <span className="otp-v3-country">
                +91
              </span>

              <input
                id="phone"
                type="tel"
                inputMode="numeric"
                autoComplete="tel-national"
                placeholder="10-digit mobile number"
                value={phone}
                maxLength={10}
                onChange={(e) =>
                  setPhone(
                    e.target.value
                      .replace(/\D/g, '')
                      .slice(0, 10)
                  )
                }
              />

            </div>

            <div
              ref={recaptchaRef}
              className="otp-v3-recaptcha"
            />

            <button
              type="submit"
              className="otp-v3-primary-button"
              disabled={loading}
            >
              <span>
                {loading
                  ? 'Sending...'
                  : 'Send verification code'}
              </span>

              {!loading && (
                <span className="otp-v3-arrow">
                  →
                </span>
              )}
            </button>

          </form>

        </div>
      )}

      {/* ============================================
          OTP SCREEN
      ============================================ */}

      {confirmation && (
        <div className="otp-v3-screen otp-screen">

          <div
            className={`otp-v3-verification-icon ${
              otpState === 'success'
                ? 'success'
                : otpState === 'bad'
                  ? 'bad'
                  : otpState === 'verifying'
                    ? 'verifying'
                    : ''
            }`}
          >
            {otpState === 'success' ? (
              <span className="otp-v3-check">
                ✓
              </span>
            ) : otpState === 'verifying' ? (
              <div className="otp-v3-loader">
                <span>✓</span>
              </div>
            ) : (
              <span>✉</span>
            )}
          </div>

          <div className="otp-v3-heading">

            <h2>
  {otpState === 'success'
    ? 'Verified!'
    : otpState === 'verifying'
      ? 'Verifying your phone'
      : 'Enter verification code'}
</h2>

<p>
  {otpState === 'success'
    ? 'Your phone number has been verified.'
    : otpState === 'verifying'
      ? 'Checking your verification code...'
      : 'We sent a 6-digit code to'}
</p>

            {otpState !== 'success' && (
              <strong className="otp-v3-phone-display">
                +91 {phone}
              </strong>
            )}

          </div>

          {otpState !== 'success' && (
            <form onSubmit={verifyOtp}>

              {/* OTP BOXES */}

              <div
                className={`otp-v3-inputs ${
  otpState === 'bad'
    ? 'shake'
    : ''
} ${
  otpState === 'verifying'
    ? 'verifying'
    : ''
} ${
  otpState === 'success'
    ? 'verified'
    : ''
}`}
                onPaste={handleOtpPaste}
              >

                {otp.map((digit, index) => (
                  <input
                    key={index}
                    ref={(element) => {
                      otpRefs.current[index] =
                        element
                    }}
                    className={
                      digit
                        ? 'filled'
                        : ''
                    }
                    type="text"
                    inputMode="numeric"
                    autoComplete={
                      index === 0
                        ? 'one-time-code'
                        : 'off'
                    }
                    maxLength={1}
                    value={digit}
                    disabled={
                      loading ||
                      otpState === 'verifying'
                    }
                    onChange={(e) =>
                      handleOtpChange(
                        index,
                        e.target.value
                      )
                    }
                    onKeyDown={(e) =>
                      handleOtpKeyDown(
                        index,
                        e
                      )
                    }
                    aria-label={`OTP digit ${
                      index + 1
                    }`}
                  />
                ))}

              </div>

              {/* VERIFY BUTTON */}

              <button
                type="submit"
                className={`otp-v3-primary-button otp-v3-verify-button ${
                  otpState === 'verifying'
                    ? 'verifying'
                    : ''
                }`}
                disabled={
                  loading ||
                  otp.join('').length !== 6
                }
              >
                {otpState === 'verifying'
                  ? 'Verifying...'
                  : 'Verify & continue'}

                {otpState !==
                  'verifying' && (
                  <span className="otp-v3-arrow">
                    →
                  </span>
                )}
              </button>

            </form>
          )}

          {/* SUCCESS SEAL */}

          {otpState === 'success' && (
            <div className="otp-v3-success-seal">
              <div className="otp-v3-success-circle">
                ✓
              </div>

              <span>
                Phone verified
              </span>
            </div>
          )}

          {/* RESEND */}

          {otpState !== 'success' && (
            <div className="otp-v3-resend">

              <span>
                Didn't receive the code?
              </span>

              {resendTimer > 0 ? (
                <span className="otp-v3-countdown">
                  Resend in {resendTimer}s
                </span>
              ) : (
                <button
                  type="button"
                  onClick={resendOtp}
                  disabled={loading}
                >
                  Resend code
                </button>
              )}

            </div>
          )}

          {/* CHANGE PHONE */}

          {otpState !== 'success' && (
            <button
              type="button"
              className="otp-v3-change-phone"
              onClick={changePhone}
              disabled={loading}
            >
              ← Change phone number
            </button>
          )}

        </div>
      )}

      {/* STATUS */}

      {message && (
        <p className="otp-v3-status">
          {message}
        </p>
      )}

      {error && (
        <p className="otp-v3-error">
          {error}
        </p>
      )}

    </div>
  )
}

export default PhoneLogin