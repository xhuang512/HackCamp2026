/* The onboarding draft.

   Every answer is written here the moment it is given, so closing the app
   halfway through step 2 and reopening it lands the student back on step 3
   with their name and schedule still filled in. Nothing reaches the backend
   until the last step calls POST /students, which then clears the draft.

   One draft per identity, keyed by the Auth0 sub (or 'guest'). Two students
   sharing a phone in demo mode cannot see each other's answers, and logging
   out and back in as someone else does not inherit a half-finished profile.

   Every read and write is wrapped: private browsing throws on localStorage
   access rather than returning null, and a throw here must not stop someone
   signing up. A lost draft costs four taps. A crash costs the demo. */

const PREFIX = 'hangout.onboarding.'

/* Bumped when the draft's shape changes. An old draft is dropped rather than
   migrated, because reading a stale shape into the form is how a half-filled
   screen ends up sending a malformed POST /students body. */
const VERSION = 1

export const LAST_STEP = 4

/** Nothing answered yet. `done` is the highest step the student finished, so
    "none of these" at step 3 is still a completed step 3, which an empty
    `tags` array on its own cannot express. */
export const EMPTY_DRAFT = {
  version: VERSION,
  done: 0,
  first_name: '',
  preset_id: null,
  free_blocks: null,
  tags: [],
  languages: [],
  ask_me_about: '',
  visibility: 'everyone',
}

function keyFor(sub) {
  return `${PREFIX}${sub}`
}

export function readDraft(sub) {
  try {
    const raw = localStorage.getItem(keyFor(sub))
    if (raw === null) return EMPTY_DRAFT
    const saved = JSON.parse(raw)
    if (saved?.version !== VERSION) return EMPTY_DRAFT
    /* Spread over the empty draft so a field added since the draft was
       written reads as unanswered instead of undefined. */
    return {
      ...EMPTY_DRAFT,
      ...saved,
      // Canonical ids changed when onboarding was connected to GET /options.
      // Preserve an in-progress answer instead of making the student repeat
      // the flow, but never send the retired aliases to POST /students.
      tags: (saved.tags ?? []).map((tag) => ({ 'first-year': 'first-term', grad: 'graduate' })[tag] ?? tag),
    }
  } catch {
    return EMPTY_DRAFT
  }
}

export function writeDraft(sub, draft) {
  try {
    localStorage.setItem(keyFor(sub), JSON.stringify({ ...draft, version: VERSION }))
  } catch {
    /* Their answers stay in React state for this session, so the signup in
       front of them still works. Only resuming after a close is lost. */
  }
}

export function clearDraft(sub) {
  try {
    localStorage.removeItem(keyFor(sub))
  } catch {
    /* A stale draft is harmless once the profile exists: GET /me says
       onboarded, so the gate never opens onboarding again. */
  }
}

/** Where to resume. One past the last finished step, clamped to the last one. */
export function resumeStep(draft) {
  return Math.min(draft.done + 1, LAST_STEP)
}

/** The POST /students body. Sends preset_id or free_blocks, never both, which
    is what the endpoint requires. */
export function toStudentBody(draft, { guest }) {
  const useBlocks = draft.preset_id === null && draft.free_blocks !== null

  return {
    first_name: draft.first_name.trim(),
    preset_id: useBlocks ? null : draft.preset_id,
    free_blocks: useBlocks ? draft.free_blocks : null,
    tags: draft.tags,
    languages: draft.languages,
    ask_me_about: draft.ask_me_about.trim() === '' ? null : draft.ask_me_about.trim(),
    visibility: draft.visibility,
    guest,
  }
}
