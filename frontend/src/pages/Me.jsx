import { useCallback, useState } from 'react'
import * as api from '../lib/api.js'
import useAsync from '../lib/useAsync.js'
import { useAuth } from '../lib/authContext.js'
import { STUDENT_TAGS } from '../lib/presets.js'
import ScreenHeader from '../components/ScreenHeader.jsx'
import StateCard from '../components/StateCard.jsx'
import Icon from '../components/Icon.jsx'
import ScheduleEditor from '../components/ScheduleEditor.jsx'

/* The mockup has no Me screen (its "Me" tab points at the onboarding
   artboard), so this is built from the privacy rules in AGENTS.md rather
   than from a drawing. Treat the layout as a placeholder and the rules as
   the part that matters:
     - the hangout count and the timetable are private to their owner
     - tags are the only thing other students see, beside the free block
     - pause and visibility are always respected by matching */

/* PATCH /me's own limits, from PatchMeRequest in backend/app/models.py.
   Enforced here so a too-long name is caught before the request rather than
   coming back as a 422 the student has to decode. */
const NAME_MAX = 40
const TAGS_MAX = 10

export default function Me() {
  const { data, error, loading, reload } = useAsync(api.getMe)
  const student = data?.student ?? null
  const auth = useAuth()
  const [pausing, setPausing] = useState(false)
  const [savingVisibility, setSavingVisibility] = useState(false)
  const [actionError, setActionError] = useState(null)
  const [scheduleOpen, setScheduleOpen] = useState(false)

  /* The canonical tag list, the same source onboarding reads. A second
     hardcoded list here is how the two drift until a saved tag stops
     matching the catalog and is silently dropped. presets.js is the offline
     fallback, not a parallel truth. */
  const catalog = useAsync(api.getOptions)
  const tagOptions =
    catalog.data?.tags ??
    STUDENT_TAGS.map((tag) => ({ id: tag.slug, label: tag.label }))
  const labelFor = (id) => tagOptions.find((tag) => tag.id === id)?.label ?? id

  /* null means the editor is closed. Opening it seeds the fields from the
     student loaded at that moment, which is why there is no effect syncing
     the two: there is no second copy of the profile sitting around going
     stale while GET /me reloads underneath it. */
  const [edit, setEdit] = useState(null)
  const [saving, setSaving] = useState(false)

  const saveProfile = useCallback(async () => {
    setSaving(true)
    setActionError(null)
    try {
      await api.patchMe({ first_name: edit.first_name.trim(), tags: edit.tags })
      setEdit(null)
      reload()
    } catch (err) {
      /* The editor stays open with their text in it. Closing it on failure
         would throw the edit away and leave them guessing what was saved. */
      setActionError(err)
    } finally {
      setSaving(false)
    }
  }, [edit, reload])

  const togglePause = useCallback(
    async (paused) => {
      setPausing(true)
      setActionError(null)
      try {
        await api.setPaused(paused)
        reload()
      } catch (err) {
        setActionError(err)
      } finally {
        setPausing(false)
      }
    },
    [reload],
  )

  const changeVisibility = useCallback(async (visibility) => {
    setSavingVisibility(true)
    setActionError(null)
    try {
      await api.patchMe({ visibility })
      reload()
    } catch (err) {
      setActionError(err)
    } finally {
      setSavingVisibility(false)
    }
  }, [reload])

  function logOut() {
    if ((student?.is_guest || auth.kind === 'guest') && !window.confirm('Logging out removes this guest session from this phone. Continue?')) return
    auth.logout()
  }

  return (
    <>
      <ScreenHeader eyebrow="Your account" title="Me" small />

      {loading && <StateCard title="Loading your profile" />}

      {error && (
        <StateCard title="Could not load your profile" onRetry={reload}>
          {error.message}
        </StateCard>
      )}

      {data?.onboarded === false && <StateCard title="No profile yet">Finish onboarding to set up your profile.</StateCard>}
      {actionError && <StateCard title="Could not save that change">{actionError.message}</StateCard>}

      {student && (
        <>
          <div className="me-id">
            <span className="me-id__avatar" aria-hidden="true">
              {student.first_name[0].toUpperCase()}
            </span>
            <div className="screen-head__text">
              <span className="screen-head__title screen-head__title--sm">
                {student.first_name}
              </span>
              <span className="screen-head__eyebrow">
                {student.is_guest ? 'Guest · ' : ''}{student.tags.map(labelFor).join(' · ')}
              </span>
            </div>
            {edit === null && (
              <button
                type="button"
                className="btn btn--ghost me-id__edit"
                onClick={() => setEdit({ first_name: student.first_name, tags: student.tags })}
              >
                Edit
              </button>
            )}
          </div>

          {edit !== null && (
            <div className="section">
              <h2 className="section__title">Edit profile</h2>

              <label className="field settings-field">
                <span className="field__label">First name</span>
                <input
                  className="field__input"
                  type="text"
                  autoComplete="given-name"
                  maxLength={NAME_MAX}
                  value={edit.first_name}
                  disabled={saving}
                  onChange={(e) => setEdit({ ...edit, first_name: e.target.value })}
                />
              </label>

              <fieldset className="choices">
                <legend className="field__label">
                  You are. This is the only thing other students see about you,
                  beside the hours you are free.
                </legend>
                <div className="chips">
                  {tagOptions.map((tag) => {
                    const on = edit.tags.includes(tag.id)
                    return (
                      <label key={tag.id} className={on ? 'chip chip--on' : 'chip'}>
                        <input
                          type="checkbox"
                          className="choice__input"
                          checked={on}
                          /* The cap is PATCH /me's, so the last box simply
                             cannot be ticked rather than the save failing. */
                          disabled={saving || (!on && edit.tags.length >= TAGS_MAX)}
                          onChange={(e) =>
                            setEdit({
                              ...edit,
                              tags: e.target.checked
                                ? [...edit.tags, tag.id]
                                : edit.tags.filter((t) => t !== tag.id),
                            })
                          }
                        />
                        <span>{tag.label}</span>
                      </label>
                    )
                  })}
                </div>
              </fieldset>

              {catalog.error && (
                <p className="note note--sm">
                  Showing the built-in tag list, because the catalog did not
                  load. Saving still works.
                </p>
              )}

              <div className="me-edit__actions">
                <button
                  type="button"
                  className="btn btn--primary btn--lg"
                  disabled={saving || edit.first_name.trim() === ''}
                  onClick={saveProfile}
                >
                  {saving ? 'Saving…' : 'Save'}
                </button>
                <button
                  type="button"
                  className="btn btn--ghost btn--lg"
                  disabled={saving}
                  onClick={() => {
                    setEdit(null)
                    setActionError(null)
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          <div className="section">
            <h2 className="section__title">Settings</h2>

            <label className="switch">
              <span className="switch__text">
                <span className="row__name">Pause suggestions</span>
                <span className="row__meta">
                  We stop putting you in groups until you turn this off.
                </span>
              </span>
              <input
                type="checkbox"
                checked={student.paused}
                disabled={pausing}
                onChange={(e) => togglePause(e.target.checked)}
              />
            </label>

            <label className="field settings-field">
              <span className="field__label">Who can match with you</span>
              <select
                className="field__input"
                value={student.visibility}
                disabled={savingVisibility}
                onChange={(event) => changeVisibility(event.target.value)}
              >
                <option value="everyone">Everyone</option>
                <option value="my_courses">People in my courses</option>
                <option value="shared_tag">People with a shared tag</option>
              </select>
            </label>

            <button
              type="button"
              className="row row--button"
              aria-expanded={scheduleOpen}
              aria-controls="schedule-editor"
              onClick={() => setScheduleOpen((open) => !open)}
            >
              <div className="row__text">
                <span className="row__name">Your timetable</span>
                <span className="row__meta">Upload and review your availability.</span>
              </div>
              <span className="row__action" aria-hidden="true">
                {scheduleOpen ? 'Close' : 'Edit schedule'}
                <span className="row__chevron">{scheduleOpen ? '−' : '›'}</span>
              </span>
            </button>

            {scheduleOpen && <ScheduleEditor />}

            <p className="note note--sm">
              <Icon name="lock" size={20} />
              Other students only see that you&apos;re free and the tags above.
            </p>
          </div>

          {/* Logging out clears the Auth0 session and any guest token, then
              the route gate shows Welcome. The profile stays, so signing back
              in skips onboarding. */}
          <button type="button" className="btn btn--outline btn--lg me-logout" onClick={logOut}>
            Log out
          </button>
        </>
      )}
    </>
  )
}
