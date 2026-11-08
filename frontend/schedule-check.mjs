/* Checks the schedule editor's validation and its no-Gemini fallback.

       npm run check:schedule

   Section 3 of docs/feature-plans.md asks for validation and the 503 case to
   be covered if the project has component tests. It has no test runner, so
   this follows signup-check.mjs: load the real module through Vite's SSR
   loader and assert on it. The rules worth pinning are pure functions, so
   none of this needs a DOM.

   What it does not cover: the click path. Exercise that on a phone, which is
   also the only place the file picker and the camera roll behave for real. */

const { createServer } = await import('vite')
const vite = await createServer({
  root: import.meta.dirname,
  server: { middlewareMode: true, hmr: false },
  appType: 'custom',
  logLevel: 'error',
})

const editor = await vite.ssrLoadModule('/src/pages/ScheduleEditor.jsx')
const { ImageReadError } = await vite.ssrLoadModule('/src/lib/image.js')
const { mergeBlocks, problemsIn, parseMessage, toStep } = await vite.ssrLoadModule(
  '/src/lib/schedule.js',
)

let failures = 0
const say = (ok, label, detail = '') => {
  if (!ok) failures++
  console.log(ok ? `ok   ${label}` : `FAIL ${label}${detail}`)
}
const block = (day, start_time, end_time) => ({ day, start_time, end_time })
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)

/* ---------- Validation before saving ---------- */

say(problemsIn([]).empty, 'an empty schedule is a problem')
say(
  !problemsIn([block(1, '09:00', '10:00')]).empty,
  'one block is enough to save',
)
say(
  problemsIn([block(1, '11:00', '10:00')]).backwards,
  'an end before its start is caught',
)
say(
  problemsIn([block(1, '10:00', '10:00')]).backwards,
  'a zero-length block is caught',
)
say(
  problemsIn([block(1, '09:00', '11:00'), block(1, '10:00', '12:00')]).overlapping,
  'two overlapping blocks on one day are caught',
)
say(
  !problemsIn([block(1, '09:00', '11:00'), block(2, '10:00', '12:00')]).overlapping,
  'the same hours on different days do not overlap',
)
/* A backwards block used to report as an overlap as well, which read as two
   separate faults for one mistake. */
say(
  !problemsIn([block(1, '11:00', '10:00'), block(1, '12:00', '13:00')]).overlapping,
  'a backwards block reports one problem, not two',
)

/* ---------- The merge the overlap error offers ---------- */

say(
  same(mergeBlocks([block(1, '09:00', '11:00'), block(1, '10:00', '12:00')]), [
    block(1, '09:00', '12:00'),
  ]),
  'overlapping blocks merge into one',
)
say(
  same(mergeBlocks([block(1, '10:00', '11:00'), block(1, '11:00', '12:00')]), [
    block(1, '10:00', '12:00'),
  ]),
  'touching blocks merge too',
)
say(
  same(mergeBlocks([block(1, '09:00', '12:00'), block(1, '10:00', '11:00')]), [
    block(1, '09:00', '12:00'),
  ]),
  'a block inside another is absorbed, not extended',
)
say(
  mergeBlocks([block(3, '09:00', '10:00'), block(1, '09:00', '10:00')])[0].day === 1,
  'merging sorts by day',
)
say(
  !problemsIn(mergeBlocks([block(1, '09:00', '11:00'), block(1, '10:00', '12:00')]))
    .overlapping,
  'merging actually clears the error it is offered for',
)

/* ---------- Times step in 15 minutes ---------- */

say(toStep('09:07') === '09:00', 'a typed 09:07 snaps back to 09:00')
say(toStep('09:08') === '09:15', 'a typed 09:08 snaps up to 09:15')
say(toStep('23:59') === '23:45', 'the last block of the day cannot pass 23:45')

/* ---------- The three parse failures, and the 503 fallback ---------- */

const offMessage = parseMessage({ status: 503 })
say(
  offMessage.includes('off right now') && offMessage.includes('by hand'),
  'a 503 says screenshots are off and the editor still works',
)
say(
  parseMessage({ status: 422 }).includes("couldn't find a timetable"),
  'a 422 asks for a clearer screenshot',
)
say(
  parseMessage({ status: 500 }).includes('still here'),
  'a 500 promises the edits are not lost',
)
say(
  parseMessage({ status: 0 }).includes('still here'),
  'an unreachable server promises the same',
)
say(
  parseMessage(new ImageReadError('decode failed')).includes('could not be read'),
  'a file the browser cannot decode gets its own message',
)

/* ---------- First paint ----------

   Catches the two ways this screen breaks without anyone clicking: a module
   that touches document or window while rendering, which kills the SSR
   check and the build's prerender, and a route that quietly falls through to
   Right now. Effects do not run here, so the first paint is the loading
   state and no request goes out. */

const React = (await import('react')).default
const { renderToStaticMarkup } = await import('react-dom/server')
const { MemoryRouter } = await import('react-router-dom')
const ScheduleEditor = editor.default

let markup = ''
let crash = null
try {
  markup = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ['/me/schedule'] },
      React.createElement(ScheduleEditor),
    ),
  )
} catch (error) {
  crash = error
}

say(crash === null, 'the editor renders without a DOM', crash ? `: ${crash.message}` : '')
say(markup.includes('Loading your timetable'), 'first paint is the loading state')
say(!markup.includes('tabbar'), 'the editor has no tab bar to slip away through')

await vite.close()
console.log(failures === 0 ? '\nall passed' : `\n${failures} failed`)
process.exit(failures === 0 ? 0 : 1)
