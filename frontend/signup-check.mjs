/* Checks the route gate's table from docs/SIGNUP.md, by rendering the real
   components through Vite's SSR loader.
 
       npm run check:signup
 
   It catches what a build does not: the gate sending a signed-in student to
   Welcome, onboarding losing a draft, /projector asking for a session, a zero
   on the aha screen. First paint only, since nothing here clicks.
 
   It runs the guest path, which is what a fresh clone has. The Auth0 path
   needs a real browser: auth0-spa-js requires window.crypto.subtle and
   refuses to load in node, by design. Exercise that one on a phone. */
const mem = new Map()
globalThis.localStorage = {
  getItem: (k) => (mem.has(k) ? mem.get(k) : null),
  setItem: (k, v) => mem.set(k, String(v)),
  removeItem: (k) => mem.delete(k),
}

/* The Auth0 path reads window.location.origin for its redirect_uri, which a
   browser always has and node does not. */
/* auth0-spa-js refuses to load without window.crypto, by design. */
globalThis.window = {
  location: { origin: 'http://localhost:5174' },
  crypto: globalThis.crypto,
  addEventListener: () => {},
  removeEventListener: () => {},
}

/* Plain imports, not absolute paths. These two lines pointed at the
   worktree this script was written in, which loaded a second copy of Vite
   and of React from another directory and failed with "Invalid hook call"
   anywhere else. */
const { createServer } = await import('vite')
const vite = await createServer({
  root: import.meta.dirname,
  server: { middlewareMode: true, hmr: false },
  appType: 'custom',
  logLevel: 'error',
})

const React = (await import('react')).default
const { renderToStaticMarkup } = await import('react-dom/server')
const { MemoryRouter } = await import('react-router-dom')
const { AuthProvider } = await vite.ssrLoadModule('/src/lib/auth.jsx')
const { AuthContext, EMPTY } = await vite.ssrLoadModule('/src/lib/authContext.js')
const App = (await vite.ssrLoadModule('/src/App.jsx')).default
const Onboarding = (await vite.ssrLoadModule('/src/pages/Onboarding.jsx')).default
const Aha = (await vite.ssrLoadModule('/src/pages/Aha.jsx')).default
const { studentCreated } = await vite.ssrLoadModule('/src/lib/fixtures.js')
const { toStudentBody } = await vite.ssrLoadModule('/src/lib/draft.js')

const h = React.createElement
const render = (route, node) =>
  renderToStaticMarkup(h(AuthProvider, null, h(MemoryRouter, { initialEntries: [route] }, node)))

let failures = 0
const say = (ok, label, detail = '') => {
  if (!ok) failures++
  console.log(ok ? `ok   ${label}` : `FAIL ${label}${detail}`)
}
const has = (html, needle, label) =>
  say(html.includes(needle), label, `  (looking for "${needle}")`)
const hasNot = (html, needle, label) => say(!html.includes(needle), label)

// 1. no session -> Welcome, and no tab bar
const welcome = render('/', h(App))
has(welcome, 'Continue as guest', 'no session shows Welcome')
hasNot(welcome, 'tabbar', 'Welcome has no tab bar')

hasNot(welcome, 'Continue with Google', 'Google button hidden without Auth0')

// 2. /projector is public: it renders with no session at all
const projector = render('/projector', h(App))
has(projector, 'UBC Meet, live at UBC', '/projector renders unsigned-in')

// 3. onboarding, as a signed-in student: four questions
const asStudent = { ...EMPTY, status: 'authed', kind: 'auth0', sub: 'auth0|abc', logout: () => {} }
const asGuest = { ...EMPTY, status: 'anon', kind: null, guestPending: true, logout: () => {} }
const onboard = (auth) =>
  renderToStaticMarkup(h(AuthContext.Provider, { value: auth }, h(Onboarding, { onDone: () => {} })))

const step1 = onboard(asStudent)
has(step1, 'What should we call you?', 'onboarding starts at the name')
has(step1, 'aria-valuetext="Step 1 of 4"', 'a student gets four questions')
hasNot(step1, 'value="Guest ', 'no guest name for a student')

// 4. the demo guest's shorter run
const guest1 = onboard(asGuest)
has(guest1, 'aria-valuetext="Step 1 of 3"', 'a guest gets three questions')
has(guest1, 'value="Guest ', 'a guest name is prefilled')

// 5. onboarding resumes where it stopped
mem.set('hangout.onboarding.auth0|abc', JSON.stringify({
  version: 1, done: 2, first_name: 'Sothea', preset_id: 'long-wednesday',
  free_blocks: null, tags: [], languages: [], ask_me_about: '', visibility: 'everyone',
}))
const step3 = onboard(asStudent)
has(step3, 'Anything we should match you on?', 'a half-finished draft resumes at step 3')
has(step3, 'aria-valuetext="Step 3 of 4"', 'resumed progress is right')
has(step3, 'Languages you speak', 'a student is asked for languages')
hasNot(guest1, 'Languages you speak', 'a guest skips languages')

// 6. the aha screen, from the real response shape
const created = studentCreated({ first_name: 'Sothea', preset_id: 'tue-thu-afternoons', tags: ['transfer'], guest: true })
const aha = renderToStaticMarkup(h(Aha, { aha: created.aha, firstName: 'Sothea', onContinue: () => {} }))
has(aha, 'You are in, Sothea', 'the aha screen greets them')
has(aha, String(created.aha.free_count), 'the aha number is the one from the response')
has(aha, 'Tuesday', 'the gap is named')
hasNot(aha, '>0<', 'no zero on the aha screen')

// 7. Gemini's review shape is translated to POST /students' established
// start/end shape. Without this, FastAPI reports both fields as required at
// the last onboarding step even though the user reviewed their schedule.
const uploaded = toStudentBody({
  first_name: 'Sothea',
  preset_id: null,
  free_blocks: [{ day: 1, start_time: '13:00', end_time: '15:00' }],
  tags: ['transfer'],
  courses: ['STAT 406'],
  languages: [],
  ask_me_about: '',
  visibility: 'everyone',
}, { guest: true })
say(
  uploaded.free_blocks[0].start === '13:00'
    && uploaded.free_blocks[0].end === '15:00'
    && !('start_time' in uploaded.free_blocks[0])
    && !('end_time' in uploaded.free_blocks[0]),
  'uploaded schedule matches POST /students',
)

await vite.close()

console.log(failures === 0 ? '\nall passed' : `\n${failures} failed`)
process.exit(failures === 0 ? 0 : 1)
