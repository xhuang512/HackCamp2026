import { useEffect, useState } from 'react'
import QRCode from 'qrcode'
import * as api from '../lib/api.js'
import StateCard from './StateCard.jsx'

export default function CheckInCode({ groupId }) {
  const [state, setState] = useState({ loading: true, code: null, image: null, error: null })
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let live = true
    let timer

    async function load() {
      try {
        const result = await api.getCheckinCode(groupId)
        const image = await QRCode.toDataURL(result.code, { width: 240, margin: 2 })
        if (!live) return
        setState({ loading: false, code: result.code, image, error: null })
        timer = window.setTimeout(load, Math.max(result.expires_in, 1) * 1000)
      } catch (error) {
        if (live) setState({ loading: false, code: null, image: null, error })
      }
    }

    load()
    return () => {
      live = false
      window.clearTimeout(timer)
    }
  }, [groupId, nonce])

  if (state.loading) return <StateCard title="Making your check-in code" />
  if (state.error) return <StateCard title="Could not make your code" onRetry={() => { setState({ loading: true, code: null, image: null, error: null }); setNonce((value) => value + 1) }}>{state.error.message}</StateCard>

  return (
    <section className="checkin-card" aria-labelledby="my-code-title">
      <h2 className="section__title" id="my-code-title">My check-in code</h2>
      <p className="row__meta">Have a groupmate scan this. It changes every 30 seconds.</p>
      <img className="checkin-code" src={state.image} alt="Your rotating group check-in QR code" />
      <details>
        <summary>Show typed code</summary>
        <code className="typed-code">{state.code}</code>
      </details>
    </section>
  )
}
