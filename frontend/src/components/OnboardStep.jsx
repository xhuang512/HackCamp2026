/* The frame every onboarding question sits in: back, progress, the question,
   the answer, one forward button.

   One question per screen. On a 390px phone that is the difference between a
   form and a conversation, and it is also why the draft matters: four small
   screens are four chances to put the phone down.

   The forward button is disabled rather than hidden when the answer is not
   valid yet, so the shape of the screen never changes under the thumb. It
   uses aria-disabled and stays focusable, because a `disabled` button cannot
   be focused and gives a screen reader nothing to explain. */

export default function OnboardStep({
  step,
  total,
  title,
  helper,
  onBack,
  backLabel = 'Back',
  onNext,
  nextLabel = 'Continue',
  nextReady = true,
  busy = false,
  error,
  children,
}) {
  return (
    <form
      className="onboard"
      onSubmit={(e) => {
        e.preventDefault()
        if (nextReady && !busy) onNext()
      }}
    >
      <div className="onboard__bar">
        <button
          type="button"
          className="onboard__back"
          onClick={onBack}
          aria-label={backLabel}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true"
            stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M15 5l-7 7 7 7" />
          </svg>
        </button>

        <div
          className="onboard__progress"
          role="progressbar"
          aria-valuemin={1}
          aria-valuemax={total}
          aria-valuenow={step}
          aria-valuetext={`Step ${step} of ${total}`}
        >
          <span
            className="onboard__progress-fill"
            style={{ inlineSize: `${(step / total) * 100}%` }}
          />
        </div>

        <span className="onboard__count">
          {step}/{total}
        </span>
      </div>

      <div className="onboard__body">
        <h1 className="onboard__title">{title}</h1>
        {helper !== undefined && <p className="onboard__helper">{helper}</p>}
        {children}
      </div>

      <div className="onboard__foot">
        {error !== undefined && error !== null && (
          <p className="onboard__error" role="alert">
            {error}
          </p>
        )}
        <button
          type="submit"
          className="btn btn--primary btn--xl"
          aria-disabled={!nextReady || busy}
        >
          {busy ? 'Saving…' : nextLabel}
        </button>
      </div>
    </form>
  )
}
