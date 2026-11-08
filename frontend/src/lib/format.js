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

/* "13:00" -> "1:00 PM". Wall-clock strings from the backend, so no Date and
   no device timezone is involved. */
export function formatClock(hhmm) {
  const [h, m] = hhmm.split(':').map(Number)
  const hour = h % 12 === 0 ? 12 : h % 12
  return `${hour}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`
}

/** { start: "13:00", end: "15:00" } -> "1:00–3:00 PM", as the redesign frames
    write a gap. The meridiem is dropped from the start when both ends share it. */
export function formatRange(gap) {
  const a = formatClock(gap.start)
  const b = formatClock(gap.end)
  return a.slice(-2) === b.slice(-2) ? `${a.slice(0, -3)}–${b}` : `${a}–${b}`
}

/** The current time in Vancouver, e.g. "12:45 PM PDT". The backend is
    Vancouver-local, so the header shows the clock the matching runs on. */
export function vancouverNow(date = new Date()) {
  return date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    timeZone: 'America/Vancouver',
    timeZoneName: 'short',
  })
}
