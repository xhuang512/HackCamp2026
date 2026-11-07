/* Loading, error and empty states. Every screen that fetches shows one of
   these rather than a blank panel, so a dead backend is obvious on the phone. */

export default function StateCard({ title, children, onRetry }) {
  return (
    <div className="state" role="status">
      <span className="state__title">{title}</span>
      {children !== undefined && <p className="state__body">{children}</p>}
      {onRetry !== undefined && (
        <button type="button" className="btn btn--ghost" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}
