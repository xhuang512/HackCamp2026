import { useCallback, useState } from 'react'
import { useLocation } from 'react-router-dom'
import * as api from '../lib/api.js'
import useAsync from '../lib/useAsync.js'
import { useAuth } from '../lib/authContext.js'
import { STUDENT_TAGS } from '../lib/presets.js'
import Icon from '../components/Icon.jsx'
import StateCard from '../components/StateCard.jsx'
import ScheduleEditor from '../components/ScheduleEditor.jsx'
import TimetableDay from '../components/TimetableDay.jsx'

/* Styled from Figma frames 8081:2 (My profile) and 8081:92 (Settings).

   Most of what those frames show is not built and is not meant to be:
   a Super Host role, pronouns, major, minor, a
   bio and a favourite spot are fields no endpoint returns. What is here is
   what the API has, wearing the frames' type, fills and corners.

   The rules below are the part that outranks the drawing:
     - the hangout count and the timetable are private to their owner
     - tags are the only thing other students see, beside the free block
     - pause and visibility are always respected by matching */

/* PATCH /me's own limits, from PatchMeRequest in backend/app/models.py.
   Enforced here so a too-long name is caught before the request rather than
   coming back as a 422 the student has to decode. */
const NAME_MAX = 40
const TAGS_MAX = 10


/* The frames' hexagonal profile stickers. The artwork is not in the repo, so
   each tag gets a plain octagon carrying its first letter: same slot and
   size, no invented icons. */
function Sticker({ label }) {
  return (
    <span className="rd-sticker">
      <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden="true">
        <polygon points="14,3 30,3 41,14 41,30 30,41 14,41 3,30 3,14" />
        <text x="22" y="28" textAnchor="middle">{label[0].toUpperCase()}</text>
      </svg>
      <span className="rd-sticker__label">{label.split(' ')[0]}</span>
    </span>
  )
}

export default function Me() {
  const { data, error, loading, reload } = useAsync(api.getMe)
  const student = data?.student ?? null
  const auth = useAuth()
  const [pausing, setPausing] = useState(false)
  const [savingVisibility, setSavingVisibility] = useState(false)
  const [actionError, setActionError] = useState(null)
  /* 'profile', 'settings' or 'timetable': the redesign's three screens. */
  const [view, setView] = useState('profile')
  const [blocks, setBlocks] = useState([])

  /* Set by ScheduleEditor as it navigates back, so the confirmation lands on
     this screen instead of flashing on the one being left. Read once per
     arrival: it lives in the history entry, so it is gone on the next open
     and there is no flag to clear. */
  const savedBlocks = useLocation().state?.scheduleSaved ?? null

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

  const back = (to) => (
    <button type="button" className="rd-back" onClick={() => { setView(to); setEdit(null) }}>
      {to === 'profile' ? '‹ My profile' : '‹ Back'}
    </button>
  )

  const problems = (
    <>
      {loading && <StateCard title="Loading your profile" />}
      {error && (
        <StateCard title="Could not load your profile" onRetry={reload}>
          {error.message}
        </StateCard>
      )}
      {data?.onboarded === false && <StateCard title="No profile yet">Finish onboarding to set up your profile.</StateCard>}
      {actionError && <StateCard title="Could not save that change">{actionError.message}</StateCard>}
    </>
  )

  /* ---------- Settings ---------- */
  if (view === 'settings') {
    return (
      <>
        {back('profile')}
        <header className="rd-head rd-head--tight"><h1 className="rd-title">Settings</h1></header>
        {problems}
        {student && (
          <>
            <section className="rd-card rd-card--section">
              <h2 className="rd-card__title">Group suggestions</h2>
              <p className="rd-card__meta">Pause matching whenever you need a break.</p>
              <button
                type="button"
                className="rd-toggle"
                aria-pressed={student.paused}
                disabled={pausing}
                onClick={() => togglePause(!student.paused)}
              >
                Pause suggestions · {student.paused ? 'On' : 'Off'}
              </button>
            </section>

            <section className="rd-card rd-card--section">
              <h2 className="rd-card__title">Who can match with you</h2>
              <label className="field settings-field">
                <span className="sr-only">Who can match with you</span>
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
              <p className="row__meta">Other students only see that you&apos;re free and the tags on your profile.</p>
            </section>

            {/* Logging out clears the Auth0 session and any guest token, then
                the route gate shows Welcome. The profile stays, so signing
                back in skips onboarding. The frame's Delete account and
                Notifications have no endpoint behind them, so are not drawn. */}
            <section className="rd-card rd-card--section">
              <h2 className="rd-card__title">Account</h2>
              <p className="rd-card__meta">
                {student.is_guest ? 'Guest account · unverified' : 'Signed in'}
              </p>
              <button type="button" className="rd-row-btn" onClick={logOut}>Sign out</button>
            </section>
          </>
        )}
      </>
    )
  }

  /* ---------- Timetable ---------- */
  if (view === 'timetable') {
    return (
      <>
        {back('profile')}
        <header className="rd-head rd-head--tight"><h1 className="rd-title">Your timetable</h1></header>
        <p className="rd-sub rd-sub--sm">
          Private · Only your shared free time is visible to others.
        </p>
        <TimetableDay blocks={blocks} />
        <ScheduleEditor onBlocksChange={setBlocks} />
      </>
    )
  }

  /* ---------- My profile ---------- */
  return (
    <>
      <header className="rd-head"><h1 className="rd-title">My profile</h1></header>
      {problems}

      {student && (
        <>
          <div className="rd-panel rd-id">
            <span className="rd-id__avatar" aria-hidden="true">
              {student.first_name[0].toUpperCase()}
            </span>
            <div className="rd-id__text">
              <span className="rd-id__name">{student.first_name}</span>
              {student.is_guest && <span className="rd-id__role">Guest</span>}
            </div>
            <div className="rd-stickers">
              {student.tags.slice(0, 3).map((tag) => <Sticker key={tag} label={labelFor(tag)} />)}
            </div>
          </div>

          {edit === null ? (
            <button
              type="button"
              className="rd-row-btn rd-row-btn--inline"
              onClick={() => setEdit({ first_name: student.first_name, tags: student.tags })}
            >
              Edit name and tags
            </button>
          ) : (
            <div className="rd-card rd-card--section">
              <h2 className="rd-card__title">Edit profile</h2>

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

          {student.favourite_spots?.length > 0 && (
            <div className="rd-panel rd-panel--grey">
              <strong className="rd-panel__title">My favourite study spot</strong>
              <span className="rd-panel__text">{student.favourite_spots[0]}</span>
            </div>
          )}

          <section className="section" aria-labelledby="badges-title">
            <h2 className="section__title" id="badges-title">Badges</h2>
            {data.badges.length === 0 ? (
              <p className="row__meta">Your check-in badges will appear here.</p>
            ) : (
              <ul className="achievements">
                {data.badges.map((badge) => (
                  <li
                    key={badge.slug}
                    className={badge.earned ? 'achievement' : 'achievement achievement--locked'}
                  >
                    <span className="achievement__icon">
                      <Icon name={badge.earned ? 'badge' : 'lock'} size={22} />
                    </span>
                    <span className="achievement__text">
                      <span className="row__name">{badge.name}</span>
                      <span className="row__meta">
                        {badge.earned
                          ? 'Earned'
                          : `${badge.progress.current} of ${badge.progress.target} check-ins`}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {savedBlocks !== null && (
            <p className="inline-message" role="status">
              Schedule saved. Right now will use your {savedBlocks} free{' '}
              {savedBlocks === 1 ? 'block' : 'blocks'} from its next open.
            </p>
          )}

          <div className="rd-panel rd-panel--grey">
            <strong className="rd-panel__title">Private to you</strong>
            <span className="rd-panel__text">
              Other students only see that you&apos;re free and your tags.
            </span>
          </div>

          <button type="button" className="btn btn--primary btn--lg btn--block rd-gap" onClick={() => setView('timetable')}>
            Timetable
          </button>

          <button type="button" className="rd-row-btn rd-row-btn--nav" onClick={() => setView('settings')}>
            Settings <span aria-hidden="true">›</span>
          </button>
        </>
      )}
    </>
  )
}
