/* Social or Study for this gap. Two real buttons carrying aria-pressed, so
   the active one is announced rather than only coloured in. */

const MODES = [
  { id: 'social', label: 'Social' },
  { id: 'study', label: 'Study' },
]

export default function ModeToggle({ value, onChange }) {
  return (
    <div className="mode-toggle" role="group" aria-label="Mode for this gap">
      {MODES.map(({ id, label }) => (
        <button
          key={id}
          type="button"
          className="mode-toggle__btn"
          aria-pressed={value === id}
          onClick={() => onChange(id)}
        >
          {/* Reinforcement only. aria-pressed above is what announces the
              state, so the tick is hidden from the accessibility tree
              rather than read out as punctuation before every label. */}
          {value === id && (
            <span className="mode-toggle__tick" aria-hidden="true">
              ✓
            </span>
          )}
          {label}
        </button>
      ))}
    </div>
  )
}
