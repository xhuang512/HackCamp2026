/* Checks the colour scheme is the app's choice and not the phone's.

       npm run check:theme

   Three regressions this catches, all of which look fine in a build:

     someone re-adds a prefers-color-scheme rule, and the toggle silently
     stops deciding anything on a dark phone;

     the storage key in index.html's pre-paint script drifts from THEME_KEY,
     so the saved choice applies one frame late, as a visible flash;

     a dark palette loses its light partner, which is how a token ends up
     the same colour in both modes and fails contrast in one of them. */

import { readFileSync } from 'node:fs'

const { createServer } = await import('vite')
const vite = await createServer({
  root: import.meta.dirname,
  server: { middlewareMode: true, hmr: false },
  appType: 'custom',
  logLevel: 'error',
})

const theme = await vite.ssrLoadModule('/src/lib/theme.js')
const tokens = readFileSync(new URL('./src/styles/tokens.css', import.meta.url), 'utf8')
const html = readFileSync(new URL('./index.html', import.meta.url), 'utf8')

let failures = 0
const say = (ok, label, detail = '') => {
  if (!ok) failures++
  console.log(ok ? `ok   ${label}` : `FAIL ${label}${detail}`)
}

/* ---------- The phone no longer decides ---------- */

/* Comments may still mention it; a rule may not. */
const rules = tokens.replace(/\/\*[\s\S]*?\*\//g, '')
say(
  !rules.includes('prefers-color-scheme'),
  'tokens.css has no prefers-color-scheme rule left',
)
say(
  rules.includes(':root[data-theme="dark"]'),
  'dark mode switches on data-theme instead',
)
say(
  (rules.match(/:root\[data-theme="dark"\]/g) || []).length === 2,
  'both dark blocks converted, the palette and the derived tokens',
)
say(rules.includes('color-scheme: light'), 'light sets color-scheme for native widgets')
say(rules.includes('color-scheme: dark'), 'dark sets it too')

/* ---------- The pre-paint script agrees with the module ---------- */

say(
  html.includes(`localStorage.getItem('${theme.THEME_KEY}')`),
  'index.html reads the same storage key as theme.js',
  ` (THEME_KEY is ${theme.THEME_KEY})`,
)
say(
  html.indexOf('<div id="root">') > html.indexOf('data-theme'),
  'the theme is set before the app element, so there is no flash',
)
say(
  (html.match(/<meta\s+name="theme-color"/g) || []).length === 1,
  'one theme-color meta, rewritten in JS rather than media-queried',
)

/* ---------- Defaults and storage ---------- */

say(theme.DEFAULT_THEME === 'light', 'the default is light, as the Figma frames are drawn')
say(theme.readTheme() === 'light', 'no saved choice reads as light')

globalThis.localStorage = {
  _v: {},
  getItem(k) { return k in this._v ? this._v[k] : null },
  setItem(k, v) { this._v[k] = String(v) },
  removeItem(k) { delete this._v[k] },
}
globalThis.localStorage.setItem(theme.THEME_KEY, 'dark')
say(theme.readTheme() === 'dark', 'a saved dark choice is read back')
globalThis.localStorage.setItem(theme.THEME_KEY, 'chartreuse')
say(theme.readTheme() === 'light', 'a junk saved value falls back to light, never crashes')

/* applyTheme with no document must be a no-op rather than a throw, or the
   SSR smoke check and any prerender die on import. */
let crash = null
try { theme.applyTheme('dark') } catch (e) { crash = e }
say(crash === null, 'applyTheme survives having no DOM', crash ? `: ${crash.message}` : '')

/* ---------- Every dark token has a light partner ---------- */

const names = (block) =>
  new Set([...block.matchAll(/^\s*(--[a-z0-9-]+)\s*:/gm)].map((m) => m[1]))
const blockAfter = (marker) => {
  const start = rules.indexOf(marker)
  return rules.slice(start, rules.indexOf('}', start))
}
const darkPalette = names(blockAfter(':root[data-theme="dark"]'))
const lightNames = new Set([
  ...names(rules.slice(0, rules.indexOf(':root[data-theme="dark"]'))),
])
const orphans = [...darkPalette].filter((n) => n !== 'color-scheme' && !lightNames.has(n))
say(orphans.length === 0, 'every dark token overrides a light one', ` orphans: ${orphans}`)

await vite.close()
console.log(failures === 0 ? '\nall passed' : `\n${failures} failed`)
process.exit(failures === 0 ? 0 : 1)
