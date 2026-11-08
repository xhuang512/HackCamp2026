import { useEffect, useState } from 'react'
import QRCode from 'qrcode'
import * as api from '../lib/api.js'
import StateCard from './StateCard.jsx'

export default function CheckInCode({ groupId }) {
  const [state, setState] = useState({
    loading: true,
    code: null,
    typed: null,
    image: null,
    error: null,
  })
  const [nonce, setNonce] = useState(0)
  const [copied, setCopied] = useState(false)

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(state.typed)
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
        setState({
          loading: false,
          code: result.code,
          typed: result.typed,
          image,
          error: null,
        })
        timer = window.setTimeout(load, Math.max(result.expires_in, 1) * 1000)
      } catch (error) {
        if (live) {
          setState({ loading: false, code: null, typed: null, image: null, error })
        }
      }
    }

    load()
    return () => {
      live = false
      window.clearTimeout(timer)
    }
  }, [groupId, nonce])

  if (state.loading) return <StateCard title="Making your check-in code" />
  if (state.error) {
    return (
      <StateCard
        title="Could not make your code"
        onRetry={() => {
          setState({ loading: true, code: null, typed: null, image: null, error: null })
          setNonce((value) => value + 1)
        }}
      >
        {state.error.message}
      </StateCard>
    )
  }

  return (
    <section className="checkin-card" aria-labelledby="my-code-title">
      <h2 className="section__title" id="my-code-title">My check-in code</h2>
      <p className="row__meta">Have a groupmate scan this. It changes every 30 seconds.</p>
      <div className="checkin-code__frame">
        <img className="checkin-code" src={state.image} alt="Your rotating group check-in QR code" />
      </div>

      {/* Out in the open, not behind a disclosure. It is the whole fallback
          for a phone whose camera will not open, and the frame prints it
          as the second thing on the screen. Six digits, spaced in threes,
          because the person reading it aloud is doing so across a table.
          `code` keeps the digits in a tabular face so 1 and 7 do not have
          to be guessed at. */}
      {state.typed !== null && (
        <div className="typed-code">
          <span className="typed-code__label">Manual check-in code</span>
          <code className="typed-code__value">
            {state.typed.slice(0, 3)} {state.typed.slice(3)}
          </code>
          <button type="button" className="btn btn--ghost copy-code" onClick={copyCode}>
            {copied ? 'Copied' : 'Copy code'}
          </button>
        </div>
      )}
    </section>
  )
}
