import { useEffect, useState } from 'react'
import QRCode from 'qrcode'
import * as api from '../lib/api.js'
import StateCard from './StateCard.jsx'

export default function CheckInCode({ groupId, meetingStart, onAvailabilityChange }) {
  const [state, setState] = useState({
    loading: true,
    code: null,
    image: null,
    joinedCount: 0,
    checkedInCount: 0,
    error: null,
  })
  const [nonce, setNonce] = useState(0)
  const [copied, setCopied] = useState(false)

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(state.code)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }

  useEffect(() => {
    let live = true
    let timer

    async function load() {
      try {
        const result = await api.getCheckinCode(groupId)
        const image = await QRCode.toDataURL(result.code, { width: 240, margin: 2 })
        if (!live) return
        onAvailabilityChange?.(groupId, true)
        setState({
          loading: false,
          code: result.code,
          image,
          joinedCount: result.joined_count,
          checkedInCount: result.checked_in_count,
          error: null,
        })
        timer = window.setTimeout(load, Math.max(result.expires_in, 1) * 1000)
      } catch (error) {
        if (!live) return
        onAvailabilityChange?.(groupId, false)
        setState((current) => ({ ...current, loading: false, code: null, image: null, error }))
      }
    }

    load()
    return () => {
      live = false
      window.clearTimeout(timer)
    }
  }, [groupId, nonce, onAvailabilityChange])

  if (state.loading) return <StateCard title="Making your check-in code" />
  if (state.error?.status === 409 && state.error.message === 'Check-in opens when the meeting starts') {
    return (
      <StateCard
        title="Check-in opens at your meeting time"
        onRetry={() => {
          setState((current) => ({ ...current, loading: true, code: null, image: null, error: null }))
          setNonce((value) => value + 1)
        }}
      >
        Your group is confirmed. The rotating QR code will become available
        {meetingStart ? ` at ${meetingStart}` : ' when the meeting starts'}.
      </StateCard>
    )
  }
  if (state.error) return <StateCard title={state.error?.status === 409 ? "Check-in is not open" : "Could not make your code"} onRetry={() => { setState((current) => ({ ...current, loading: true, code: null, image: null, error: null })); setNonce((value) => value + 1) }}>{state.error.message}</StateCard>

  return (
    <section className="checkin-card" aria-labelledby="my-code-title">
      <h2 className="section__title" id="my-code-title">Your check-in code</h2>
      <p className="row__meta">
        Show this to a groupmate when they arrive. It changes every 30 seconds.
      </p>
      <p className="inline-message" role="status">
        {state.checkedInCount} of {state.joinedCount} checked in
      </p>
      <div className="checkin-code__frame">
        <img className="checkin-code" src={state.image} alt="Your rotating group check-in QR code" />
      </div>
      <details>
        <summary>Show manual code</summary>
        {/* The signed hc1 token, not a PIN: the backend accepts nothing else. */}
        <div className="typed-code">
          <span className="typed-code__label">Manual check-in code</span>
          <code className="typed-code__value typed-code__value--token">{state.code}</code>
          <button type="button" className="btn btn--ghost copy-code" onClick={copyCode}>
            {copied ? 'Copied' : 'Copy full code'}
          </button>
        </div>
      </details>
    </section>
  )
}
