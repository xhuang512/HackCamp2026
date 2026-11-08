/* Display helpers. No network, no state. */

const DAYS = {
  mon: 'Monday', tue: 'Tuesday', wed: 'Wednesday',
  thu: 'Thursday', fri: 'Friday', sat: 'Saturday', sun: 'Sunday',
}

/** "13:00" -> { h: 1, m: "00", suffix: "pm" } */
function parse(hhmm) {
  const [h, m] = hhmm.split(':').map(Number)
  return {
    h: h % 12 === 0 ? 12 : h % 12,
    m: String(m).padStart(2, '0'),
    suffix: h < 12 ? 'am' : 'pm',
  }
}

function clock({ h, m }) {
  return m === '00' ? `${h}` : `${h}:${m}`
}

/**
 * { start: "13:00", end: "15:00" } -> "1 to 3pm"
 * Drops the meridiem on the start when both ends share it.
 */
export function formatGap(gap) {
  const a = parse(gap.start)
  const b = parse(gap.end)
  const head = a.suffix === b.suffix ? clock(a) : `${clock(a)}${a.suffix}`
  return `${head} to ${clock(b)}${b.suffix}`
}

/** "tue" -> "Tuesday" */
export function formatDay(day) {
  return DAYS[day] ?? day
}
