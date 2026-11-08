import { useCallback, useEffect, useRef, useState } from 'react'
import * as api from '../lib/api.js'
import useAsync from '../lib/useAsync.js'
import { draftKeyFor, useAuth } from '../lib/authContext.js'
import {
  EMPTY_DRAFT,
  clearDraft,
  readDraft,
  resumeStep,
  toStudentBody,
  writeDraft,
} from '../lib/draft.js'
import { LANGUAGES, PRESETS, STUDENT_TAGS, VISIBILITY_OPTIONS } from '../lib/presets.js'
import CourseInput from '../components/CourseInput.jsx'
import OnboardStep from '../components/OnboardStep.jsx'

/* Onboarding, four questions for a student and three for a demo guest.

   Nothing is sent to the backend until the last step. Every answer goes into
   a localStorage draft the moment it is given, so the route gate can drop
   someone back on the step they stopped at. See src/lib/draft.js.

   `onDone` hands the POST /students response up to the gate, which owns the
   aha screen. This page does not navigate; the gate decides what comes next
   from the same three facts it always uses. */

const NAME_MAX = 40
const ASK_MAX = 120

export default function Onboarding({ onDone }) {
  const auth = useAuth()
  const guest = auth.kind === 'guest' || auth.guestPending
  const sub = draftKeyFor(auth)

  /* Guests skip languages, "ask me about" and the visibility question, which
     keep their defaults. Three screens is what gets a stage audience from the
     join QR to a group card inside 30 seconds. */
  const total = guest ? 3 : 4

  const [draft, setDraft] = useState(() => {
    const saved = readDraft(sub)
    if (saved.first_name !== '' || saved.done > 0) return saved
    /* A guest should not have to type a name to get into the demo, but they
       can change it. The number keeps two guests in the same room apart. */
    return guest
      ? { ...EMPTY_DRAFT, first_name: `Guest ${1 + Math.floor(Math.random() * 99)}` }
      : EMPTY_DRAFT
  })
  const [step, setStep] = useState(() => Math.min(resumeStep(readDraft(sub)), total))
  const [busy, setBusy] = useState(false)
  const [submitError, setSubmitError] = useState(null)
  /* Set when POST /students refused only because of the courses. */
  const [termBlocked, setTermBlocked] = useState(false)
  const catalog = useAsync(api.getOptions)
  const tagOptions =
    catalog.data?.tags ??
    STUDENT_TAGS.map((tag) => ({ id: tag.slug, label: tag.label }))
  const languageOptions =
    catalog.data?.languages ??
    LANGUAGES.map((language) => ({ id: language.code, label: language.name }))

  /* Moving between questions is a navigation, so say where we landed.
     Without this a screen reader user hears nothing change. */
  const focusRef = useRef(null)
  useEffect(() => {
    focusRef.current?.focus()
  }, [step])

  /* One writer for both the draft and its backup, so no screen can update
     the answer and forget to persist it. */
  const answer = useCallback(
    (patch) => {
      setDraft((prev) => {
        const next = { ...prev, ...patch }
        writeDraft(sub, next)
        return next
      })
    },
    [sub],
  )


  const back = useCallback(() => {
    if (step > 1) {
      setStep((s) => s - 1)
      return
    }
    /* Back from the first question means "I did not mean to sign in". The
       draft stays: if they come straight back their name is still there. */
    auth.logout()
  }, [auth, step])

  const submit = useCallback(
    async (final) => {
      setBusy(true)
      setSubmitError(null)
      setTermBlocked(false)
      try {
        const allowedTags = new Set(tagOptions.map((option) => option.id))
        const allowedLanguages = new Set(languageOptions.map((option) => option.id))
        const canonical = {
          ...final,
          tags: final.tags
            .map((tag) => ({ 'first-year': 'first-term', grad: 'graduate' })[tag] ?? tag)
            .filter((tag) => allowedTags.has(tag)),
          languages: final.languages.filter((language) => allowedLanguages.has(language)),
        }
        const out = await api.createStudent(toStudentBody(canonical, { guest }))
        /* Clear the draft only once the profile exists. Clearing it first
           would lose every answer if the request failed. */
        clearDraft(sub)
        /* A guest's token arrives in that response. Adopting it before the
           gate re-checks GET /me is what makes the next request
           authenticated. */
        if (out.guest_token) auth.adoptGuestToken()
        onDone(out)
      } catch (cause) {
        /* The server rejects courses outright when its CURRENT_TERM is
           unset, and that 422 fails the whole request. Signup is the one
           place in the app with nothing behind it, so rather than leaving
           someone stuck behind a backend variable they cannot set, offer to
           drop the courses and keep every other answer. Offered, not done
           silently: dropping what they typed without saying so is worse
           than the error. */
        /* Keyed on the message rather than the status. The backend answers
           503 here, not 422, because an unset environment variable is the
           server's fault and not the caller's, and that is easy to assume
           wrongly: this check was written against 422 and silently never
           fired until a real request proved otherwise. */
        if (/CURRENT_TERM/i.test(cause?.message ?? '')) {
          setTermBlocked(true)
          setSubmitError(
            'The server cannot store courses yet, because its CURRENT_TERM is not set. Finish without them, or set it on the backend and try again.',
          )
        } else {
          setSubmitError(
            cause?.status === 0
              ? 'Could not reach the server. Your answers are saved.'
              : cause?.message ?? 'That did not save. Your answers are kept, try again.',
          )
        }
      } finally {
        setBusy(false)
      }
    },
    [auth, guest, languageOptions, onDone, sub, tagOptions],
  )

  /* The one way forward. On the last question it submits instead of stepping,
     so a guest's shorter run finishes at step 3 without a second code path. */
  const advance = useCallback(
    (patch = {}) => {
      const next = { ...draft, ...patch, done: Math.max(step, draft.done) }
      writeDraft(sub, next)
      setDraft(next)
      if (step >= total) submit(next)
      else setStep(step + 1)
    },
    [draft, step, sub, submit, total],
  )

  /* Shown only after POST /students has refused the courses specifically,
     on whichever step is the last one for this student: a guest finishes at
     3, a student at 4. It resubmits everything else, so nothing already
     answered is lost. */
  const termHatch = termBlocked ? (
    <button
      type="button"
      className="btn btn--outline"
      disabled={busy}
      onClick={() => advance({ courses: [] })}
    >
      {busy ? 'Finishing…' : 'Finish without courses'}
    </button>
  ) : null

  const frame = {
    step,
    total,
    onBack: back,
    backLabel: step === 1 ? 'Back to the welcome screen' : 'Back',
    busy,
  }

  if (step === 1) {
    const name = draft.first_name.trim()
    return (
      <OnboardStep
        {...frame}
        title="What should we call you?"
        helper="Your first name. Only the people in your group ever see it."
        nextReady={name.length >= 1 && name.length <= NAME_MAX}
        onNext={() => advance({ first_name: draft.first_name })}
      >
        <label className="field">
          <span className="field__label">First name</span>
          <input
            ref={focusRef}
            className="field__input"
            type="text"
            name="first_name"
            autoComplete="given-name"
            maxLength={NAME_MAX}
            value={draft.first_name}
            onChange={(e) => answer({ first_name: e.target.value })}
          />
        </label>
      </OnboardStep>
    )
  }

  if (step === 2) {
    return (
      <OnboardStep
        {...frame}
        title="When are you on campus?"
        helper="Pick the week that looks most like yours. You can change it later."
        nextReady={draft.preset_id !== null || draft.free_blocks !== null}
        onNext={() => advance()}
      >
        {/* A radio group, not buttons: one choice out of many, and arrow keys
            should move between them. */}
        <fieldset className="choices" ref={focusRef} tabIndex={-1}>
          <legend className="sr-only">Preset schedules</legend>
          {PRESETS.map((preset) => (
            <label
              key={preset.id}
              className={
                draft.preset_id === preset.id ? 'choice choice--on' : 'choice'
              }
            >
              <input
                type="radio"
                name="preset"
                className="choice__input"
                checked={draft.preset_id === preset.id}
                onChange={() => answer({ preset_id: preset.id, free_blocks: null })}
              />
              <span className="choice__text">
                <span className="choice__label">{preset.label}</span>
                <span className="choice__blurb">{preset.blurb}</span>
              </span>
            </label>
          ))}
        </fieldset>

        <p className="note note--sm">
          Uploading a screenshot of your timetable comes later. It will show
          you what it read before anything is saved.
        </p>
      </OnboardStep>
    )
  }

  if (step === 3) {
    const picked = draft.tags.length > 0 || draft.courses.length > 0 || draft.done >= 3
    return (
      <OnboardStep
        {...frame}
        title="Anything we should match you on?"
        helper="This is the only thing other students see about you, beside the hours you are free."
        nextReady={picked}
        nextLabel={guest ? 'Finish' : 'Continue'}
        onNext={() => advance()}
        error={submitError}
      >
        <fieldset className="choices" ref={focusRef} tabIndex={-1}>
          <legend className="field__label">You are</legend>
          {/* Wrapped, not stacked. The frame lays these out as a run of
              chips, and six full-width rows pushed Continue off a 390px
              screen before the student had answered anything. */}
          <div className="chips">
          {tagOptions.map((tag) => (
            <label
              key={tag.id}
              className={
                draft.tags.includes(tag.id) ? 'chip chip--on' : 'chip'
              }
            >
              <input
                type="checkbox"
                className="choice__input"
                checked={draft.tags.includes(tag.id)}
                onChange={(e) =>
                  answer({
                    tags: e.target.checked
                      ? [...draft.tags, tag.id]
                      : draft.tags.filter((t) => t !== tag.id),
                  })
                }
              />
              <span>{tag.label}</span>
            </label>
          ))}
          </div>
        </fieldset>

        {/* "None of these" is a real answer, not an empty one. It marks the
            step finished so the gate does not send them back here, which an
            empty tag list on its own cannot do. */}
        <button
          type="button"
          className="btn btn--ghost"
          onClick={() => advance({ tags: [] })}
        >
          None of these
        </button>

        {/* Courses belong to this question rather than a step of their own.
            The step already asks what to match on, and AGENTS.md pins a
            guest at three screens to get a stage audience from the join QR
            to a group card inside 30 seconds. A fifth question would spend
            that budget. */}
        <CourseInput
          value={draft.courses}
          onChange={(courses) => answer({ courses })}
        />

        {termHatch}

        {!guest && (
          <>
            <fieldset className="choices">
              <legend className="field__label">Languages you speak (optional)</legend>
              <div className="chips">
                {languageOptions.map((lang) => (
                  <label
                    key={lang.id}
                    className={
                      draft.languages.includes(lang.id) ? 'chip chip--on' : 'chip'
                    }
                  >
                    <input
                      type="checkbox"
                      className="choice__input"
                      checked={draft.languages.includes(lang.id)}
                      onChange={(e) =>
                        answer({
                          languages: e.target.checked
                            ? [...draft.languages, lang.id]
                            : draft.languages.filter((c) => c !== lang.id),
                        })
                      }
                    />
                    <span>{lang.label}</span>
                  </label>
                ))}
              </div>
            </fieldset>

            <label className="field">
              <span className="field__label">Ask me about (optional)</span>
              <input
                className="field__input"
                type="text"
                maxLength={ASK_MAX}
                placeholder="film cameras"
                value={draft.ask_me_about}
                onChange={(e) => answer({ ask_me_about: e.target.value })}
              />
              <span className="field__count">
                {draft.ask_me_about.length}/{ASK_MAX}
              </span>
            </label>
          </>
        )}
      </OnboardStep>
    )
  }

  return (
    <OnboardStep
      {...frame}
      title="Who can we match you with?"
      helper="You can change this any time in the Me tab."
      nextLabel="Finish"
      onNext={() => advance()}
      error={submitError}
    >
      <fieldset className="choices" ref={focusRef} tabIndex={-1}>
        <legend className="sr-only">Who can match with you</legend>
        {VISIBILITY_OPTIONS.map((option) => (
          <label
            key={option.value}
            className={
              draft.visibility === option.value ? 'choice choice--on' : 'choice'
            }
          >
            <input
              type="radio"
              name="visibility"
              className="choice__input"
              checked={draft.visibility === option.value}
              onChange={() => answer({ visibility: option.value })}
            />
            <span className="choice__text">
              <span className="choice__label">{option.label}</span>
              <span className="choice__blurb">{option.blurb}</span>
            </span>
          </label>
        ))}
      </fieldset>

      {termHatch}
    </OnboardStep>
  )
}
