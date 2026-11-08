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

  function cameraError(error) {
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      return 'Camera scanning needs HTTPS. Open the Cloudflare tunnel URL, not your computer\'s http:// LAN address.'
    }
    if (error?.name === 'NotAllowedError') {
      return 'Camera permission is blocked. Allow camera access for this site in your browser settings, then try again.'
    }
    if (error?.name === 'NotFoundError') {
      return 'No camera was found on this device. Paste a groupmate\'s current code below.'
    }
    if (error?.name === 'NotReadableError') {
      return 'Another app may be using the camera. Close it and try again.'
    }
    return 'The camera could not start. Enter a groupmate\'s six-digit code below.'
  }

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
      const earned = result.new_badges?.map((badge) => badge.name) ?? []
      setMessage(
        earned.length > 0
          ? `You earned ${earned.join(' and ')}.`
          : result.counted
            ? 'You both checked in.'
            : 'You were already checked in together.',
      )
      onCheckedIn(result)
    } catch (error) {
      setMessage(
        error.status === 422
          ? `${error.message} Use a current code from a different phone signed into this same group.`
          : error.message,
      )
    } finally {
      setBusy(false)
    }
  }

  async function start() {
    setMessage(null)
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setMessage(cameraError())
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' } },
        audio: false,
      })
      streamRef.current = stream
      setCamera(true)
      const video = videoRef.current
      video.srcObject = stream
      await video.play()
      const canvas = document.createElement('canvas')
      const context = canvas.getContext('2d', { willReadFrequently: true })
      if (context === null) throw new Error('Canvas is unavailable')
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
    } catch (error) {
      stop()
      setMessage(cameraError(error))
    }
  }

  function typed(event) {
    event.preventDefault()
    submit(new FormData(event.currentTarget).get('code'))
  }

  return (
    <section className="checkin-card" aria-labelledby="scan-title">
      <h2 className="section__title" id="scan-title">Scan a groupmate</h2>
      <video
        ref={videoRef}
        className="scanner-video"
        playsInline
        muted
        autoPlay
        hidden={!camera}
        aria-label="Camera preview for QR scanning"
      />
      {camera ? (
        <>
          <button type="button" className="btn btn--ghost" onClick={stop}>Stop camera</button>
        </>
      ) : (
        <button type="button" className="btn btn--primary btn--lg" onClick={start} disabled={busy}>Open camera</button>
      )}
      <form className="typed-form" onSubmit={typed}>
        <label className="field">
          <span className="field__label">Six-digit check-in code</span>
          <input
            className="field__input"
            name="code"
            required
            autoComplete="off"
            autoCapitalize="none"
            spellCheck="false"
            inputMode="numeric"
            placeholder="e.g. 482 716"
          />
        </label>
        <button type="submit" className="btn btn--ghost" disabled={busy}>Check in with code</button>
      </form>
      {message && <p className="inline-message" role="status">{message}</p>}
      <p className="row__meta">
        Two different joined members are required. Your own code cannot check you in.
      </p>
    </section>
  )
}
