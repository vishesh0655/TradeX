import { useEffect, useRef, useState } from 'react'
import './OtpVerify.css'

const OTP_LENGTH = 6

function OtpVerify({
  phone = '+1 415 ●●● 0142',
  onVerified,
  onResend,
}) {
  const [otp, setOtp] = useState(['', '', '', '', '', ''])
  const [phase, setPhase] = useState('idle')
  const [drawSlot, setDrawSlot] = useState(null)
  const [countdown, setCountdown] = useState(30)

  const inputsRef = useRef([])
  const timersRef = useRef([])

  const clearTimers = () => {
    timersRef.current.forEach(clearTimeout)
    timersRef.current = []
  }

  const focusInput = (index) => {
    if (index >= 0 && index < OTP_LENGTH) {
      inputsRef.current[index]?.focus()
    }
  }

  const triggerOutline = (index) => {
    setDrawSlot(null)

    requestAnimationFrame(() => {
      setDrawSlot(index)
    })
  }

  const startSuccessAnimation = () => {
    if (phase !== 'idle') return

    setPhase('orbit')

    const spinTimer = setTimeout(() => {
      setPhase('spin')
    }, 750)

    const verdictTimer = setTimeout(() => {
      setPhase('verdict')
    }, 1650)

    const screwTimer = setTimeout(() => {
      setPhase('screw')
    }, 2500)

    const successTimer = setTimeout(() => {
      setPhase('success')

      if (typeof onVerified === 'function') {
        onVerified(otp.join(''))
      }
    }, 3300)

    timersRef.current.push(
      spinTimer,
      verdictTimer,
      screwTimer,
      successTimer
    )
  }

  const checkComplete = (nextOtp) => {
    return nextOtp.every(
      (digit) => digit !== ''
    )
  }

  const handleChange = (index, value) => {
    if (phase !== 'idle') return

    const digits = value.replace(/\D/g, '')

    if (!digits) return

    /*
      Handles browser/SMS autofill where the
      complete 6-digit code can arrive at once.
    */
    if (digits.length > 1) {
      const cleanCode = digits
        .slice(0, OTP_LENGTH)
        .split('')

      const nextOtp = [
        '',
        '',
        '',
        '',
        '',
        '',
      ]

      cleanCode.forEach((digit, i) => {
        nextOtp[i] = digit
      })

      setOtp(nextOtp)

      triggerOutline(
        cleanCode.length - 1
      )

      focusInput(
        Math.min(
          cleanCode.length,
          OTP_LENGTH - 1
        )
      )

      if (cleanCode.length === OTP_LENGTH) {
        setTimeout(startSuccessAnimation, 300)
      }

      return
    }

    const digit = digits.slice(-1)

    const nextOtp = [...otp]

    nextOtp[index] = digit

    setOtp(nextOtp)

    triggerOutline(index)

    if (index < OTP_LENGTH - 1) {
      focusInput(index + 1)
    }

    if (checkComplete(nextOtp)) {
      setTimeout(startSuccessAnimation, 300)
    }
  }

  const handleKeyDown = (index, event) => {
    if (phase !== 'idle') return

    if (event.key === 'Backspace') {
      event.preventDefault()

      const nextOtp = [...otp]

      if (otp[index]) {
        nextOtp[index] = ''
        setOtp(nextOtp)
        return
      }

      if (index > 0) {
        nextOtp[index - 1] = ''
        setOtp(nextOtp)
        focusInput(index - 1)
      }

      return
    }

    if (event.key === 'ArrowLeft') {
      event.preventDefault()
      focusInput(index - 1)
      return
    }

    if (event.key === 'ArrowRight') {
      event.preventDefault()
      focusInput(index + 1)
      return
    }

    if (
      event.key.length === 1 &&
      !/[0-9]/.test(event.key)
    ) {
      event.preventDefault()
    }
  }

  const handlePaste = (event) => {
    event.preventDefault()

    if (phase !== 'idle') return

    const pasted = event.clipboardData
      .getData('text')
      .replace(/\D/g, '')
      .slice(0, OTP_LENGTH)

    if (!pasted) return

    const nextOtp = [
      '',
      '',
      '',
      '',
      '',
      '',
    ]

    pasted
      .split('')
      .forEach((digit, index) => {
        nextOtp[index] = digit
      })

    setOtp(nextOtp)

    triggerOutline(
      pasted.length - 1
    )

    focusInput(
      Math.min(
        pasted.length,
        OTP_LENGTH - 1
      )
    )

    if (pasted.length === OTP_LENGTH) {
      setTimeout(startSuccessAnimation, 300)
    }
  }

  const handleFill = async () => {
    if (phase !== 'idle') return

    const demoCode = '471947'

    setOtp([
      '',
      '',
      '',
      '',
      '',
      '',
    ])

    for (
      let index = 0;
      index < demoCode.length;
      index++
    ) {
      await new Promise((resolve) => {
        setTimeout(resolve, 150)
      })

      setOtp((current) => {
        const next = [...current]
        next[index] = demoCode[index]
        return next
      })

      triggerOutline(index)
    }

    focusInput(5)

    setTimeout(
      startSuccessAnimation,
      350
    )
  }

  const handleResend = () => {
    if (countdown > 0) return

    setCountdown(30)

    if (typeof onResend === 'function') {
      onResend()
    }
  }

  /*
    Resend countdown
  */
  useEffect(() => {
    if (countdown <= 0) return

    const timer = setInterval(() => {
      setCountdown((current) => {
        if (current <= 1) {
          clearInterval(timer)
          return 0
        }

        return current - 1
      })
    }, 1000)

    return () => clearInterval(timer)
  }, [countdown])

  /*
    Initial focus
  */
  useEffect(() => {
    focusInput(0)

    return () => {
      clearTimers()
    }
  }, [])

  const orbitAngles = [
    -90,
    -30,
    30,
    90,
    150,
    210,
  ]

  const getOrbitStyle = (index) => {
    const angle = orbitAngles[index]

    const radius = 88

    const radians =
      (angle * Math.PI) / 180

    return {
      '--orbit-x': `${
        Math.cos(radians) * radius
      }px`,
      '--orbit-y': `${
        Math.sin(radians) * radius
      }px`,
    }
  }

  const pageClass = [
    'otp-card',
    `otp-phase-${phase}`,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className="otp-page">

      <div className={pageClass}>

        <div className="otp-grip" />

        <div className="otp-content">

          {/* ============================
              HEADING
          ============================ */}

          <div className="otp-heading">

            <h1>
              {phase === 'success'
                ? 'Verified successfully'
                : 'Verify your number'}
            </h1>

            <p>
              {phase === 'success' ? (
                'Your number has been verified.'
              ) : (
                <>
                  Enter the 6-digit code we sent to{' '}
                  <strong>{phone}</strong>.
                </>
              )}
            </p>

          </div>

          {/* ============================
              OTP STAGE
          ============================ */}

          <div className="otp-stage">

            {/* Orbit */}
            <div className="otp-orbit-ring" />

            {/* Center hub */}
            <div className="otp-hub" />

            {/* OTP slots */}
            <div className="otp-slots">

              {otp.map((digit, index) => (

                <div
                  key={index}
                  className={[
                    'otp-slot',
                    drawSlot === index
                      ? 'otp-slot-draw'
                      : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  style={getOrbitStyle(index)}
                >

                  {/* SVG outline */}

                  <svg
                    className="otp-outline"
                    viewBox="0 0 100 100"
                    preserveAspectRatio="none"
                    aria-hidden="true"
                  >
                    <rect
                      x="1"
                      y="1"
                      width="98"
                      height="98"
                      rx="17"
                      ry="17"
                    />
                  </svg>

                  {/* Real input */}

                  <input
                    ref={(element) => {
                      inputsRef.current[index] =
                        element
                    }}
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    maxLength={6}
                    autoComplete={
                      index === 0
                        ? 'one-time-code'
                        : 'off'
                    }
                    value={digit}
                    disabled={
                      phase !== 'idle'
                    }
                    onChange={(event) =>
                      handleChange(
                        index,
                        event.target.value
                      )
                    }
                    onKeyDown={(event) =>
                      handleKeyDown(
                        index,
                        event
                      )
                    }
                    onPaste={handlePaste}
                    aria-label={
                      `OTP digit ${index + 1}`
                    }
                  />

                  <span className="otp-digit">
                    {digit}
                  </span>

                </div>

              ))}

            </div>

          </div>

          {/* ============================
              NORMAL MESSAGE
          ============================ */}

          {phase !== 'success' && (

            <div className="otp-message">

              <div>

                <span className="otp-message-label">
                  MESSAGE · OTP
                </span>

                <span className="otp-message-text">
                  Your 6-digit verification code.
                </span>

              </div>

              <button
                type="button"
                onClick={handleFill}
                disabled={phase !== 'idle'}
              >
                Fill
              </button>

            </div>

          )}

          {/* ============================
              RESEND
          ============================ */}

          {phase === 'idle' && (

            <div className="otp-resend">

              <span>
                Didn't receive the code?
              </span>

              {countdown > 0 ? (

                <span className="otp-countdown">
                  Resend in {countdown}s
                </span>

              ) : (

                <button
                  type="button"
                  onClick={handleResend}
                >
                  Resend code
                </button>

              )}

            </div>

          )}

          {/* ============================
              ERROR
          ============================ */}

          {phase === 'error' && (

            <div className="otp-error-message">
              Incorrect verification code
            </div>

          )}

          {/* ============================
              SUCCESS
          ============================ */}

          {phase === 'success' && (

            <div className="otp-success">

              <div className="otp-seal">

                <div className="otp-seal-ring ring-one" />
                <div className="otp-seal-ring ring-two" />

                <svg
                  viewBox="0 0 40 40"
                  className="otp-check"
                  aria-hidden="true"
                >
                  <path
                    d="M10 21 L17 28 L31 12"
                  />
                </svg>

              </div>

              {/* Sparks */}

              <div className="otp-sparks">

                {Array.from(
                  { length: 30 },
                  (_, index) => (
                    <span
                      key={index}
                      style={{
                        '--spark-angle': `${
                          index * 12
                        }deg`,
                        '--spark-delay': `${
                          index * 18
                        }ms`,
                      }}
                    />
                  )
                )}

              </div>

              <div className="otp-secure">
                🔒 Verified and secure
              </div>

              <button
                type="button"
                className="otp-continue"
                onClick={() => {
                  if (
                    typeof onVerified ===
                    'function'
                  ) {
                    onVerified(otp.join(''))
                  }
                }}
              >
                Continue
              </button>

            </div>

          )}

        </div>

      </div>

    </div>
  )
}

export default OtpVerify
