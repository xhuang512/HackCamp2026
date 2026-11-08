import { useEffect, useRef, useState } from 'react'
import jsQR from 'jsqr'
import * as api from '../lib/api.js'

export default function CheckInScanner({ groupId, onCheckedIn }) {
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const frameRef = useRef(null)
  const [camera, setCamera] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)

  function stop() {
    window.cancelAnimationFrame(frameRef.current)
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    setCamera(false)
  }

  useEffect(() => stop, [])

  async function submit(code) {
    if (!code || busy) return
    setBusy(true)
    setMessage(null)
    try {
      const result = await api.postCheckin(groupId, code.trim())
      stop()
      setMessage(result.counted ? 'You both checked in.' : 'You were already checked in together.')
      onCheckedIn(result)
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy(false)
    }
  }

  async function start() {
    setMessage(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
      streamRef.current = stream
      setCamera(true)
      await new Promise((resolve) => window.requestAnimationFrame(resolve))
      const video = videoRef.current
      video.srcObject = stream
      await video.play()
      const canvas = document.createElement('canvas')
      const context = canvas.getContext('2d', { willReadFrequently: true })
      const scan = () => {
        if (!streamRef.current || busy) return
        if (video.readyState >= 2) {
          canvas.width = video.videoWidth
          canvas.height = video.videoHeight
          context.drawImage(video, 0, 0)
          const pixels = context.getImageData(0, 0, canvas.width, canvas.height)
          const found = jsQR(pixels.data, pixels.width, pixels.height)
          if (found?.data) {
            stop()
            submit(found.data)
            return
          }
        }
        frameRef.current = window.requestAnimationFrame(scan)
      }
      frameRef.current = window.requestAnimationFrame(scan)
    } catch {
      stop()
      setMessage('Camera access did not start. Use the typed code below.')
    }
  }

  function typed(event) {
    event.preventDefault()
    submit(new FormData(event.currentTarget).get('code'))
  }

  return (
    <section className="checkin-card" aria-labelledby="scan-title">
      <h2 className="section__title" id="scan-title">Scan a groupmate</h2>
      {camera ? (
        <>
          <video ref={videoRef} className="scanner-video" playsInline muted aria-label="Camera preview for QR scanning" />
          <button type="button" className="btn btn--ghost" onClick={stop}>Stop camera</button>
        </>
      ) : (
        <button type="button" className="btn btn--primary btn--lg" onClick={start} disabled={busy}>Open camera</button>
      )}
      <form className="typed-form" onSubmit={typed}>
        <label className="field">
          <span className="field__label">Or enter their code</span>
          <input className="field__input" name="code" required autoComplete="off" />
        </label>
        <button type="submit" className="btn btn--ghost" disabled={busy}>Check in</button>
      </form>
      {message && <p className="inline-message" role="status">{message}</p>}
    </section>
  )
}
