import { formatDay, formatGap } from '../lib/format.js'
import { STUDENT_TAGS } from '../lib/presets.js'
import Icon from '../components/Icon.jsx'

/* Shown once, straight after onboarding, never again.

   It answers the only question a student has after typing their name into
   something: is anyone actually here? So it is one number, big, from the
   POST /students response. The backend promises that number is never zero: if
   nobody shares their next gap it counts their busiest-overlap gap instead.

   `aha` is { gap, free_count, same_tag_count, tag }. */

export default function Aha({ aha, firstName, onContinue }) {
  const tagLabel =
    STUDENT_TAGS.find((t) => t.slug === aha.tag)?.label.toLowerCase() ?? null

  return (
    <div className="aha">
      <div className="aha__top">
        <span className="aha__eyebrow">
          {firstName === undefined ? 'You are in' : `You are in, ${firstName}`}
        </span>

        <p className="aha__number">{aha.free_count}</p>
        <h1 className="aha__line">
          people share your {formatDay(aha.gap.day)}{' '}
          {formatGap({ start: aha.gap.start, end: aha.gap.end ?? aha.gap.start })} gap
        </h1>

        {aha.tag !== null && aha.same_tag_count > 0 && (
          <p className="aha__sub">
            {aha.same_tag_count} of them {aha.same_tag_count === 1 ? 'is a' : 'are'}{' '}
            {tagLabel} {aha.same_tag_count === 1 ? 'student' : 'students'} like you.
          </p>
        )}
      </div>

      <p className="note note--sm">
        <Icon name="lock" size={20} />
        Nobody sees your timetable. Other students only see that you are free
        and the tags you picked.
      </p>

      <button type="button" className="btn btn--primary btn--xl" onClick={onContinue}>
        See your first group
      </button>
    </div>
  )
}
