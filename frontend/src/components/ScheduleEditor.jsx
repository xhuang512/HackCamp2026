import { useEffect, useRef, useState } from 'react'
import * as api from '../lib/api.js'

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const ACCEPTED_IMAGES = 'image/png,image/jpeg,image/webp'
const MAX_BLOCKS = 35

export default function ScheduleEditor({
  initialBlocks = [],
  onConfirm = null,
  requireBlocks = false,
  onBlocksChange = null,
}) {
  const editorRef = useRef(null)
  const inputRef = useRef(null)
  const [parsing, setParsing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState(null)
  const [blocks, setBlocks] = useState(() => initialBlocks.map((block) => ({ ...block })))
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(false)

  // Lets a screen draw the same blocks (the timetable day view) without a
  // second copy of the state.
  useEffect(() => {
    onBlocksChange?.(blocks)
  }, [blocks, onBlocksChange])

  // The timetable disclosure is near the bottom of the mobile Me screen.
  // Without bringing the newly mounted panel into view, it opens underneath
  // the fixed tab bar and the tap appears to have done nothing.
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      editorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      editorRef.current?.focus({ preventScroll: true })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [])

  async function parse(event) {
    const image = event.target.files?.[0]
    if (!image) return
    setParsing(true)
    setError(null)
    setSaved(false)
    try {
      const parsed = await api.parseSchedule(image)
      setResult(parsed)
      setBlocks(parsed.suggested_free_blocks.map((block) => ({ ...block })))
    } catch (err) {
      setResult(null)
      setBlocks([])
      setError(err)
    } finally {
      setParsing(false)
      // The browser should not retain the selected screenshot after upload.
      event.target.value = ''
    }
  }

  function changeBlock(index, field, value) {
    setBlocks((current) => current.map((block, blockIndex) => (
      blockIndex === index
        ? { ...block, [field]: field === 'day' ? Number(value) : value }
        : block
    )))
    setSaved(false)
  }

  function removeBlock(index) {
    setBlocks((current) => current.filter((_block, blockIndex) => blockIndex !== index))
    setSaved(false)
  }

  function addBlock() {
    if (blocks.length >= MAX_BLOCKS) return
    setBlocks((current) => [
      ...current,
      { day: 0, start_time: '12:00', end_time: '13:00' },
    ])
    setSaved(false)
  }

  async function save() {
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      if (onConfirm !== null) {
        await onConfirm(blocks)
      } else {
        const response = await api.updateSchedule(blocks)
        setBlocks(response.free_blocks.map((block) => ({ ...block })))
      }
      setSaved(true)
    } catch (err) {
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section
      ref={editorRef}
      className="schedule-editor"
      id="schedule-editor"
      aria-labelledby="schedule-title"
      tabIndex={-1}
    >
      <div>
        <h3 className="section__title" id="schedule-title">Update your timetable</h3>
        <p className="row__meta">
          Your screenshot is sent to Google Gemini for extraction, is not stored,
          and never becomes visible to other students. Review every suggested free
          block before saving.
        </p>
      </div>

      <input
        ref={inputRef}
        className="sr-only"
        type="file"
        accept={ACCEPTED_IMAGES}
        onChange={parse}
        disabled={parsing || saving}
        aria-label="Choose a timetable screenshot"
      />
      <button
        type="button"
        className="btn btn--outline"
        onClick={() => inputRef.current?.click()}
        disabled={parsing || saving}
      >
        {parsing ? 'Reading screenshot…' : result ? 'Choose another screenshot' : 'Upload screenshot'}
      </button>

      {error && <p className="inline-message" role="alert">{error.message}</p>}

      {result && (
        <>
          <div className="schedule-summary" aria-live="polite">
            <strong>{result.timed_events.length} timed events found</strong>
            <span className="row__meta">
              Suggestions use {result.matching_window.timezone} wall-clock time.
            </span>
          </div>

          {result.warnings.length > 0 && (
            <div className="schedule-warnings">
              <strong>Check these details</strong>
              <ul>
                {result.warnings.map((warning) => <li key={warning}>{warning}</li>)}
              </ul>
            </div>
          )}

          <div className="schedule-events">
            <h4>Events read from the image</h4>
            {result.timed_events.length === 0 ? (
              <p className="row__meta">No timed events were confidently extracted.</p>
            ) : (
              <ul className="schedule-event-list">
                {result.timed_events.map((event, index) => (
                  <li key={`${event.weekday}-${event.start_time}-${event.title}-${index}`}>
                    <strong>{event.title}</strong>
                    <span>{event.weekday.toUpperCase()} · {event.start_time}–{event.end_time}</span>
                  </li>
                ))}
              </ul>
            )}
            {result.all_day_events.length > 0 && (
              <>
                <p className="row__meta">
                  All-day events are shown for review but are not automatically treated as confirmed unavailability.
                </p>
                <ul className="schedule-event-list">
                  {result.all_day_events.map((event, index) => (
                    <li key={`${event.weekday}-${event.title}-${index}`}>
                      <strong>{event.title}</strong>
                      <span>{event.weekday.toUpperCase()} · all day</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        </>
      )}

      {(result !== null || blocks.length > 0) && (
        <>
          <div className="schedule-review">
            <div className="schedule-review__head">
              <div>
                <h4>Suggested free blocks</h4>
                <p className="row__meta">These are suggestions, not confirmed availability, until you save.</p>
              </div>
              <button
                type="button"
                className="btn btn--ghost"
                onClick={addBlock}
                disabled={saving || blocks.length >= MAX_BLOCKS}
              >
                Add block
              </button>
            </div>

            {blocks.length === 0 && <p className="row__meta">No free blocks selected.</p>}
            <div className="schedule-blocks">
              {blocks.map((block, index) => (
                <div className="schedule-block" key={index}>
                  <label>
                    <span className="sr-only">Day</span>
                    <select
                      className="field__input"
                      value={block.day}
                      onChange={(event) => changeBlock(index, 'day', event.target.value)}
                      disabled={saving}
                    >
                      {DAY_NAMES.map((day, dayIndex) => <option value={dayIndex} key={day}>{day}</option>)}
                    </select>
                  </label>
                  <label>
                    <span className="sr-only">Start time</span>
                    <input
                      className="field__input"
                      type="time"
                      value={block.start_time}
                      onChange={(event) => changeBlock(index, 'start_time', event.target.value)}
                      disabled={saving}
                      required
                    />
                  </label>
                  <span aria-hidden="true">–</span>
                  <label>
                    <span className="sr-only">End time</span>
                    <input
                      className="field__input"
                      type="time"
                      value={block.end_time}
                      onChange={(event) => changeBlock(index, 'end_time', event.target.value)}
                      disabled={saving}
                      required
                    />
                  </label>
                  <button
                    type="button"
                    className="btn btn--ghost schedule-block__remove"
                    onClick={() => removeBlock(index)}
                    disabled={saving}
                    aria-label={`Remove ${DAY_NAMES[block.day]} ${block.start_time} to ${block.end_time}`}
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          </div>

          <button
            type="button"
            className="btn btn--primary btn--lg"
            onClick={save}
            disabled={saving || parsing || (requireBlocks && blocks.length === 0)}
          >
            {saving
              ? 'Saving availability…'
              : onConfirm === null
                ? 'Save reviewed availability'
                : 'Use reviewed availability'}
          </button>
          <p className="row__meta">
            Saved blocks repeat weekly for matching until you replace them. Existing group invitations and confirmed groups are not cancelled.
          </p>
          {saved && (
            <p className="inline-message" role="status">
              {onConfirm === null
                ? 'Schedule saved. Matching will use these reviewed blocks.'
                : 'Reviewed availability selected. Continue when you are ready.'}
            </p>
          )}
        </>
      )}
    </section>
  )
}
