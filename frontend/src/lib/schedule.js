/* The free-block rules the schedule editor enforces, kept out of the
   component so they can be read and tested on their own.

   These mirror ScheduleUpdateRequest in backend/app/routers/schedule.py. The
   backend stays the authority: it rejects the same three things. Checking
   here as well is what turns "422, free blocks must not overlap" into a
   sentence with a fix button next to it. */

import { ImageReadError } from './image.js'

export const DAYS = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
]

/* PUT /me/schedule's own cap. Enforced in the editor so the Add button stops
   rather than the save failing with a 422 to decode. */
export const MAX_BLOCKS = 35
export const STEP_MINUTES = 15
export const DAY_END = 23 * 60 + 45

export function toMinutes(value) {
  const [hours, minutes] = value.split(':')
  return Number(hours) * 60 + Number(minutes)
}

export function toClock(minutes) {
  const clamped = Math.max(0, Math.min(DAY_END, minutes))
  const hours = Math.floor(clamped / 60)
  return `${String(hours).padStart(2, '0')}:${String(clamped % 60).padStart(2, '0')}`
}

/* An <input type="time"> with step=900 still accepts a typed 09:07 in some
   browsers, and the backend takes any HH:MM, so the grid is kept here too.
   Otherwise "free 09:07 to 10:52" ends up on somebody's group card. */
export function toStep(value) {
  return toClock(Math.round(toMinutes(value) / STEP_MINUTES) * STEP_MINUTES)
}

export function sortBlocks(blocks) {
  return [...blocks].sort(
    (a, b) =>
      a.day - b.day ||
      toMinutes(a.start_time) - toMinutes(b.start_time) ||
      toMinutes(a.end_time) - toMinutes(b.end_time),
  )
}

/* Overlaps are the one validation error with a fix the screen can offer, so
   this returns the merged set rather than just a boolean. Touching blocks
   (10:00-11:00 and 11:00-12:00) merge too: the backend allows them, but as
   two rows they say nothing the one row does not. */
export function mergeBlocks(blocks) {
  const merged = []
  for (const block of sortBlocks(blocks)) {
    const last = merged[merged.length - 1]
    if (
      last !== undefined &&
      last.day === block.day &&
      toMinutes(block.start_time) <= toMinutes(last.end_time)
    ) {
      if (toMinutes(block.end_time) > toMinutes(last.end_time)) {
        last.end_time = block.end_time
      }
      continue
    }
    merged.push({ ...block })
  }
  return merged
}

export function problemsIn(blocks) {
  const backwards = blocks.some(
    (block) => toMinutes(block.end_time) <= toMinutes(block.start_time),
  )
  /* Only compare blocks that are the right way round. A backwards block
     reports its own problem, and reporting it twice reads as two faults. */
  const sane = blocks.filter(
    (block) => toMinutes(block.end_time) > toMinutes(block.start_time),
  )
  return {
    empty: blocks.length === 0,
    backwards,
    overlapping: mergeBlocks(sane).length !== sane.length,
  }
}

/** The message for a failed parse, from docs/feature-plans.md section 3.

    The 503 wording is the load-bearing one: with no Gemini key configured
    the editor is still a schedule editor, and the sentence has to say so or
    a student reads it as the whole screen being broken. */
export function parseMessage(error) {
  if (error instanceof ImageReadError) {
    return 'That image could not be read on this phone. A PNG or JPEG screenshot works.'
  }
  if (error?.status === 503) {
    return 'Reading screenshots is off right now. You can edit your free time by hand below.'
  }
  if (error?.status === 422) {
    return "We couldn't find a timetable in that image. Try a clearer screenshot of your week view."
  }
  return 'Something went wrong. Your changes are still here.'
}
