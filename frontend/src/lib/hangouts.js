/* Shared helpers for hangout pins. No React, no DOM.

   The label is defined once and used in three places: the pin's
   aria-label, the pin's popup, and the sheet's button list. Keeping them
   identical is the point, so a screen-reader user and a sighted user are
   told the same thing. */

import { formatGap } from './format.js'

/** "until 3pm" from a hangout's end time. */
export function untilLabel(hangout) {
  /* formatGap drops the meridiem on the start when both ends share it, so
     feed it a zero-length range to get just the end, formatted. */
  return formatGap({ start: hangout.end, end: hangout.end }).split(' to ')[1]
}

/** The accessible name for one hangout. Carries no student names. */
export function hangoutLabel(hangout) {
  const mode = hangout.mode === 'study' ? 'Study' : 'Social'
  const people = hangout.size === 1 ? '1 person' : `${hangout.size} people`
  return `${mode} hangout at ${hangout.building.name}, ${people}, until ${untilLabel(hangout)}`
}

/** The short line under the place name in the sheet list. */
export function hangoutMeta(hangout) {
  const people = hangout.size === 1 ? '1 person' : `${hangout.size} people`
  return `${hangout.mode}, ${people}, until ${untilLabel(hangout)}`
}
