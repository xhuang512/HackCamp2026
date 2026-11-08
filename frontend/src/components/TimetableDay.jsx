import { useState } from 'react'

/* The redesign's "Day view": Mon to Fri tabs over an hour grid.

   The frame also draws class blocks (MATH 100, WRDS 150). No endpoint
   returns parsed classes after the screenshot step, and the screenshot is
   deliberately not stored, so only the free blocks the student has reviewed
   or saved in this session can be drawn. Nothing is invented. */

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
const FULL = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
const FIRST = 8
const LAST = 20
const ROW = 32

function hours(hhmm) {
  const [h, m] = hhmm.split(':').map(Number)
  return h + m / 60
}

function label(hour) {
  const h = hour % 12 === 0 ? 12 : hour % 12
  return `${h} ${hour < 12 ? 'AM' : 'PM'}`
}

export default function TimetableDay({ blocks }) {
  const [day, setDay] = useState(() => {
    const today = (new Date().getDay() + 6) % 7
    return today < 5 ? today : 0
  })
  const todays = blocks.filter((block) => Number(block.day) === day)

  return (
    <section className="rd-day" aria-label="Day view">
      <div className="rd-tabs" role="tablist" aria-label="Day">
        {DAYS.map((name, index) => (
          <button
            key={name}
            type="button"
            role="tab"
            aria-selected={day === index}
            className="rd-tabs__tab"
            onClick={() => setDay(index)}
          >
            {name}
          </button>
        ))}
      </div>

      <h3 className="rd-h2">{FULL[day]} · Day view</h3>

      <div className="rd-grid" style={{ height: (LAST - FIRST) * ROW + ROW }}>
        {Array.from({ length: LAST - FIRST + 1 }, (_, i) => FIRST + i).map((hour) => (
          <div className="rd-grid__row" key={hour} style={{ top: (hour - FIRST) * ROW }}>
            <span className="rd-grid__label">{label(hour)}</span>
          </div>
        ))}
        {todays.map((block, index) => {
          const top = (Math.max(hours(block.start_time), FIRST) - FIRST) * ROW
          const bottom = (Math.min(hours(block.end_time), LAST) - FIRST) * ROW
          if (bottom <= top) return null
          return (
            <div className="rd-grid__block" key={index} style={{ top, height: bottom - top }}>
              <strong>Free</strong>
              <span>{block.start_time}–{block.end_time}</span>
            </div>
          )
        })}
      </div>

      {todays.length === 0 && (
        <p className="row__meta">
          No free blocks to show for {FULL[day]}. Upload a screenshot or add a block below.
        </p>
      )}
    </section>
  )
}
