/* Shown while Auth0 restores the session and GET /me answers.

   It exists so the welcome screen never flashes at a student who is already
   signed in. That flash is worse than it sounds on a phone: it reads as being
   logged out, and the reflex is to tap the sign-in button, which starts a
   redirect the app did not need.

   role="status" with aria-busy, so a screen reader announces the wait instead
   of reading an empty page. */

export default function Splash({ label = 'Loading' }) {
  return (
    <div className="splash" role="status" aria-busy="true">
      <span className="splash__name">Hangout</span>
      <span className="splash__label">{label}</span>
    </div>
  )
}
