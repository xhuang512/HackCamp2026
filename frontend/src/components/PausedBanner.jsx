/* "You are paused" on Right now, with one tap to come back.

   Pausing is a privacy setting the matcher always respects, so a paused
   student gets no group card and the screen would otherwise look broken. The
   banner is the explanation, and it sits above the screen rather than inside
   it so Right now does not have to know about account state.

   Non-blocking by design: the tabs, the map and the Me tab all still work. */

export default function PausedBanner({ onResume, busy = false }) {
  return (
    <div className="banner" role="status">
      <span className="banner__text">
        You are paused, so we are not putting you in groups.
      </span>
      <button
        type="button"
        className="btn btn--ghost"
        onClick={onResume}
        aria-disabled={busy}
      >
        {busy ? 'Resuming…' : 'Resume'}
      </button>
    </div>
  )
}
