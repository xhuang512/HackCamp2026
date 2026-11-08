import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import * as api from '../lib/api.js'
import useAsync from '../lib/useAsync.js'
import { shrinkForUpload } from '../lib/image.js'
import {
  DAYS,
  DAY_END,
  MAX_BLOCKS,
  STEP_MINUTES,
  mergeBlocks,
  parseMessage,
  problemsIn,
  sortBlocks,
  toClock,
  toMinutes,
  toStep,
} from '../lib/schedule.js'
import ScreenHeader from '../components/ScreenHeader.jsx'
import StateCard from '../components/StateCard.jsx'

/* Section 3 of docs/feature-plans.md. The student uploads a timetable
   screenshot, corrects what Gemini read, and saves.

   Two rules shape everything below.

   PUT /me/schedule replaces the whole schedule rather than merging into it.
   So this screen must open with the blocks GET /me returned, and a failure
   anywhere must leave the student's edits on screen. Clearing them and
   saving is how somebody loses the schedule they picked at onboarding
   without ever being asked.

   With no Gemini key the screen is still a schedule editor. The key is not
   configured on every machine, and a stage demo that cannot edit free time
   by hand is worse than one that cannot read screenshots. Nothing here is
   gated on a parse having happened. */

function ScheduleForm({ initialBlocks }) {
  const navigate = useNavigate()
  const fileRef = useRef(null)
  const [blocks, setBlocks] = useState(() => sortBlocks(initialBlocks))
  const [parsing, setParsing] = useState(false)
  const [parseError, setParseError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [warnings, setWarnings] = useState([])

  /* "Unsaved" is a comparison against what the server gave us, not a flag set
     by every keystroke. Typing 10:00 over 10:00, or deleting a block and
     adding it back, leaves nothing to warn about. */
  const saved = useMemo(() => JSON.stringify(sortBlocks(initialBlocks)), [initialBlocks])
  const dirty = JSON.stringify(sortBlocks(blocks)) !== saved
  const problems = problemsIn(blocks)
  const invalid = problems.empty || problems.backwards || problems.overlapping

  /* Covers a reload, a closed tab and the phone's own back gesture, which
     between them are most of the ways out of a half-finished edit. The
     browser shows its own wording; the string only has to be non-empty. */
  useEffect(() => {
    if (!dirty) return undefined
    const warn = (event) => {
      event.preventDefault()
      event.returnValue = ''
      return ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const leave = useCallback(() => {
    if (dirty && !window.confirm('Leave without saving your free time?')) return
    navigate('/me')
  }, [dirty, navigate])

  async function parse(event) {
    const chosen = event.target.files?.[0]
    /* Clear it straight away, so picking the same file twice after a failure
       still fires a change, and so the browser holds no screenshot. */
    event.target.value = ''
    if (!chosen) return

    setParsing(true)
    setParseError(null)
    setSaveError(null)
    try {
      const parsed = await api.parseSchedule(await shrinkForUpload(chosen))
      /* Replaced, not added to. The screenshot is the whole week, so merging
         it into what was there would double every block they already had. */
      setBlocks(sortBlocks(parsed.suggested_free_blocks.map((block) => ({ ...block }))))
      setWarnings(parsed.warnings ?? [])
    } catch (error) {
      /* The blocks on screen are deliberately untouched. A parse that fails
         must not cost the student what they already had. */
      setParseError(error)
    } finally {
      setParsing(false)
    }
  }

  function change(index, field, value) {
    if (value === '') return
    setBlocks((current) =>
      current.map((block, at) =>
        at === index ? { ...block, [field]: toStep(value) } : block,
      ),
    )
  }

  function remove(index) {
    setBlocks((current) => current.filter((_block, at) => at !== index))
  }

  function add(day) {
    setBlocks((current) => {
      if (current.length >= MAX_BLOCKS) return current
      const onDay = current.filter((block) => block.day === day)
      const after = onDay.reduce(
        (latest, block) => Math.max(latest, toMinutes(block.end_time)),
        12 * 60,
      )
      const start = Math.min(after, DAY_END - 60)
      return sortBlocks([
        ...current,
        { day, start_time: toClock(start), end_time: toClock(start + 60) },
      ])
    })
  }

  async function save() {
    setSaving(true)
    setSaveError(null)
    try {
      const response = await api.saveSchedule(sortBlocks(blocks))
      /* Navigating with the confirmation in the URL keeps it on the screen
         the student lands on, rather than flashing it here on the way out. */
      navigate('/me', { state: { scheduleSaved: response.free_blocks.length } })
    } catch (error) {
      setSaveError(error)
    } finally {
      setSaving(false)
    }
  }

  const full = blocks.length >= MAX_BLOCKS

  return (
    <>
      <p className="note note--sm">
        Your timetable is private. Other students only ever see the hours you
        are free, never your classes. A screenshot goes to Gemini to be read
        and is not stored anywhere.
      </p>

      <section className="section" aria-labelledby="read-title">
        <h2 className="section__title" id="read-title">Read from a screenshot</h2>
        <p className="row__meta">
          A week view from Workday works best. Check what it read before you
          save, because it does get times wrong.
        </p>

        {/* The input is driven by the button beside it, because a bare file
            input cannot be given a 44px target or the app's own type. */}
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          onChange={parse}
          disabled={parsing || saving}
          className="schedule-file"
          aria-label="Choose a timetable screenshot"
        />
        <button
          type="button"
          className="btn btn--outline btn--lg"
          onClick={() => fileRef.current?.click()}
          disabled={parsing || saving}
        >
          {parsing ? 'Reading your timetable…' : 'Choose a screenshot'}
        </button>

        {/* Several seconds on venue wifi, so it says so rather than just
            sitting there disabled. */}
        <p className="inline-message" role="status" aria-live="polite">
          {parsing ? 'Reading your timetable… this takes a few seconds.' : ''}
        </p>

        {parseError !== null && (
          <p className="inline-message inline-error" role="alert">
            {parseMessage(parseError)}
          </p>
        )}

        {warnings.length > 0 && (
          <div className="schedule-warnings">
            <p className="row__name">Worth a second look</p>
            <ul>
              {warnings.map((warning) => <li key={warning}>{warning}</li>)}
            </ul>
          </div>
        )}
      </section>

      <section className="section" aria-labelledby="blocks-title">
        <h2 className="section__title" id="blocks-title">When you are free</h2>

        {problems.empty && (
          <p className="inline-message" role="status">
            No free blocks yet. Add one below, or read them from a screenshot.
          </p>
        )}

        {DAYS.map((name, day) => {
          const onDay = blocks
            .map((block, index) => ({ block, index }))
            .filter(({ block }) => block.day === day)

          return (
            <div className="schedule-day" key={name}>
              <h3 className="schedule-day__name">{name}</h3>

              {onDay.length === 0 && (
                <p className="row__meta">Nothing yet.</p>
              )}

              {onDay.map(({ block, index }, position) => (
                <div className="schedule-block" key={index}>
                  <input
                    className="field__input schedule-block__time"
                    type="time"
                    step={STEP_MINUTES * 60}
                    value={block.start_time}
                    disabled={saving}
                    onChange={(event) => change(index, 'start_time', event.target.value)}
                    aria-label={`${name} block ${position + 1} starts at`}
                  />
                  <span className="schedule-block__to">to</span>
                  <input
                    className="field__input schedule-block__time"
                    type="time"
                    step={STEP_MINUTES * 60}
                    value={block.end_time}
                    disabled={saving}
                    onChange={(event) => change(index, 'end_time', event.target.value)}
                    aria-label={`${name} block ${position + 1} ends at`}
                  />
                  <button
                    type="button"
                    className="btn btn--ghost schedule-block__remove"
                    onClick={() => remove(index)}
                    disabled={saving}
                    aria-label={`Remove ${name} ${block.start_time} to ${block.end_time}`}
                  >
                    Remove
                  </button>
                </div>
              ))}

              <button
                type="button"
                className="btn btn--ghost schedule-day__add"
                onClick={() => add(day)}
                disabled={saving || full}
              >
                Add a free block
              </button>
            </div>
          )
        })}

        {full && (
          <p className="row__meta">
            That is the most blocks a schedule can hold. Remove one to add
            another.
          </p>
        )}
      </section>

      {problems.backwards && (
        <p className="inline-message inline-error" role="alert">
          One block ends before it starts. Fix it to save.
        </p>
      )}

      {problems.overlapping && (
        <div className="inline-message inline-error" role="alert">
          <p>Two blocks on the same day overlap.</p>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => setBlocks(mergeBlocks(blocks))}
            disabled={saving}
          >
            Merge them into one
          </button>
        </div>
      )}

      {saveError !== null && (
        <p className="inline-message inline-error" role="alert">
          {saveError?.status === 422
            ? saveError.message
            : 'Something went wrong. Your changes are still here.'}
        </p>
      )}

      <div className="schedule-actions">
        <button
          type="button"
          className="btn btn--primary btn--lg"
          onClick={save}
          disabled={saving || parsing || invalid || !dirty}
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button
          type="button"
          className="btn btn--outline btn--lg"
          onClick={leave}
          disabled={saving}
        >
          {dirty ? 'Discard changes' : 'Back'}
        </button>
      </div>

      <p className="note note--sm">
        Saved blocks repeat every week until you change them. Groups you have
        already joined are not cancelled.
      </p>
    </>
  )
}

export default function ScheduleEditor() {
  const { data, error, loading, reload } = useAsync(api.getMe)

  return (
    <>
      <ScreenHeader eyebrow="Your timetable" title="Free time" small />

      {loading && <StateCard title="Loading your timetable" />}

      {error !== null && (
        <StateCard title="Could not load your timetable" onRetry={reload}>
          {error.message}
        </StateCard>
      )}

      {/* Both schedule routes need a finished profile, so a student who
          somehow reaches this URL mid-onboarding is told why, not shown an
          editor whose save would 401. */}
      {data !== null && data.onboarded === false && (
        <StateCard title="No profile yet">
          Finish onboarding and your schedule editor appears here.
        </StateCard>
      )}

      {/* Mounted only once the real blocks are in hand, so the form seeds its
          state from them in useState and needs no effect syncing a second
          copy. An editor that opens empty and then fills in is an editor that
          can be saved empty in the gap. */}
      {data?.student != null && (
        <ScheduleForm initialBlocks={data.student.free_blocks ?? []} />
      )}
    </>
  )
}
