# Plan to proceed: aligning `feat/integrate` with the design

Date: 2026-11-08 (America/Vancouver)
Based on: the Figma-to-frontend audit of `feat/integrate` at `73dd44f`.
Status: proposal. Nothing here has been implemented or approved.

## 1. Where things stand

- `feat/integrate` has the working product: QR check-in, map, Gemini schedule
  upload and review, schedule sync. Its UI is the original "Hangout" styling.
- The UBC Meet restyle is already written on `origin/feat/figma-design`
  (10 commits: tokens, Inter, Welcome, Right now, check-in, Map, Me,
  Onboarding). `origin/feat/badges` contains the same commits.
- The two branches forked at `01bf1bc`. A trial merge conflicts in
  `backend/app/models.py`, `backend/app/routers/groups.py`,
  `frontend/src/components/CheckInCode.jsx` and `frontend/src/lib/api.js`.
- That branch also adds a six-digit typed check-in code, which `feat/integrate`
  does not support and which `AGENTS.md` does not mention.
- I could not open Figma. Design facts come from `docs/design-report.md` on
  `origin/feat/figma-design` and are unchecked against the file.

## 2. Decisions needed first

Nothing below should start until these are answered. Each blocks specific work.

| # | Decision | Options | Recommendation | Blocks |
|---|---|---|---|---|
| D1 | Is UBC Meet mobile (nodes `8064`, `8068`, `8081`, `8099`) the final design? | Yes / Campus Café / other | Yes, it is the only high-fidelity 390×844 set. Get the designer to confirm. | Steps 2, 7 |
| D2 | Six-digit typed check-in code | Keep `hc1` token / adopt six digits | Keep `hc1`. Six digits is about 20 bits and nothing rate-limits `POST /groups/{id}/checkin`. If wanted, add a rate limit first. | Step 2 conflict resolution |
| D3 | Product name | Hangout / UBC Meet / Campus Café | Team call. Domain is `ubcmeet.fit`. Touches `index.html`, meta tags, manifest, Welcome copy. | Step 7 |
| D4 | Tab labels | "Right now · Map · Me" / "Groups · Map · My profile" | Match the design once D1 is yes. One line in `TabBar.jsx`. | Step 7 |
| D5 | Badges | Out of MVP / include | Out of scope here. A teammate owns it. `AGENTS.md` says no badges, so keep it separate. | Nothing here |
| D6 | Desktop finder | No / yes | No. Not an approved product. | Nothing here |
| D7 | Sign-in wording | Guest only for the demo / UBC email | Keep guest for the demo. UBC email is paused in `docs/signup.md`. | Welcome copy |

## 3. Sequence

Each step ends with something checkable. Do them in order. Steps 3 to 6 can be
split between people once step 2 is done.

### Step 1. Freeze and snapshot

- Confirm D1 and D2.
- Make sure nobody pushes to `main`. Per `docs/HANDOFF.md`, do not merge
  `feat/integrate` until the full phone demo passes.
- Note that the deployed `ubcmeet.fit` serves `feat/figma-design` from a
  checkout (per the design report), not `feat/integrate`. Anyone testing the
  live site is testing the other branch.

### Step 2. Reconcile the branches

Goal: one branch that has both the working integration and the restyle.

1. Create a new branch from `feat/integrate`, for example
   `feat/integrate-design`. Do not rebase the shared branches.
2. Merge `origin/feat/figma-design` into it.
3. Resolve the four conflicts:
   - `models.py`, `routers/groups.py`: keep this branch's lifecycle and
     check-in behavior. Take from the other branch only the lifecycle-refresh
     work (`test_lifecycle_refresh.py`) if it is still wanted.
   - `CheckInCode.jsx`, `api.js`: keep this branch's `hc1` token and its
     `joined_count`, `checked_in_count`, `my_state` handling. Apply the
     restyle on top.
   - If D2 is "keep `hc1`", drop commit `2e577cb`'s `codes.py` change and the
     `typed` field. Keep only its visual changes to the check-in panels.
4. Run backend tests from `backend/` and `npm run lint`, `npm run build`,
   `npm run check:signup`.

Done when: tests and build pass, and the manual-code field still says
"Paste the full hc1… code".

### Step 3. Fix check-in states (frontend)

Files: `RightNow.jsx`, `CheckInCode.jsx`, `CheckInScanner.jsx`.

- Only show the check-in panels when `group.state` is confirmed or active, not
  just when `my_state` is joined.
- Handle each 409 meaning explicitly: not confirmed yet, opens at meeting time,
  window ended, no longer eligible. Show a plain message for each, with no
  Retry where retrying cannot help.
- Show the start time in 12-hour form, matching the rest of the app.
- Poll `GET /me/now` while the student is joined, so the card's
  "N of M checked in" and `my_state` update when someone scans you.

Done when: with two phones, scanning one updates the other's card within one
poll interval, and a forming group shows a message instead of an error card.

### Step 4. Make the map say what it counts (frontend)

Files: `MapPage.jsx`, `lib/hangouts.js`.

- The backend count is joined members of confirmed or active groups today at a
  building. Change "free nearby", "people free" and "Where people are free
  right now" to wording like "in a confirmed group at this building".
- Keep pending invitations out of every count, as the backend already does.
- Keep the 3-person minimum.

Done when: every string on the map describes what `/map` actually returns.

### Step 5. Schedule persistence (backend plus frontend)

Problem: after saving a schedule and reloading, the editor shows nothing.

- Backend: add a read endpoint for the caller's confirmed free blocks, for
  example `GET /me/schedule`, same shape as the `PUT` body. Add a test.
- Frontend: add `getSchedule` in `api.js`, pass the result as `initialBlocks`
  to `ScheduleEditor` in `Me.jsx`, and show a read-only summary of confirmed
  availability.
- Check the Gemini path with a real key in a safe environment. Not tested yet.

Done when: save, reload, and the saved blocks are shown.

### Step 6. Stage-screen and data readiness

- `Projector.jsx`: hide the "Reset demo data" button behind a query flag or a
  confirm step, so it cannot be tapped on the public screen.
- Data: confirm with the backend owner that the shared Supabase project is on
  `schema.sql`, and seed the real building list. `/options` currently returns
  only The Nest, so Start-a-group has one choice. Verify the building
  coordinates in `mapConfig.js` and the `buildings` rows.
- Do not write to Supabase from tests or audits unless
  `RUN_SUPABASE_INTEGRATION` and its confirmation variables are set on a
  disposable project.

### Step 7. Remaining visual alignment

After D1, D3, D4 are answered:

- Verify the restyle against each frame at 390px, in light and dark mode.
- Pause control: replace the bare checkbox with the switch styling.
- Fix "1 timed events found" pluralization.
- Apply the agreed product name and tab labels.
- Welcome illustration, if the designer wants it.
- Add the favourite-spots editor on Me only if the team wants it.

### Step 8. Full verification

Run the demo from `AGENTS.md` over HTTPS (`./scripts/share-demo.sh`) at a 390px
phone viewport:

1. Two distinct guests sign up with presets.
2. They land in the same confirmed group.
3. Each scans the other's QR, and the typed code works too.
4. Right now, the map and the projector counts all move.
5. Upload a timetable screenshot, review, save, reload.
6. Pause, then confirm no group is offered. Change visibility and confirm it
   persists.

Lint and build passing is not evidence for any of this.

## 4. Who can work in parallel

| Track | Steps | Needs |
|---|---|---|
| Integration owner | 1, 2, 8 | D1, D2 |
| Frontend | 3, 4, 7 | Step 2 done |
| Backend | 5 (endpoint), 6 (data), rate limit if D2 changes | None |
| Designer | Confirm D1, D3, D4. Review step 7 screenshots. | None |
| Badge teammate | Separate. Do not touch badge files from this plan. | None |

## 5. What not to do

- Do not merge to `main` before step 8 passes.
- Do not adopt the six-digit code without a rate limit and a team decision.
- Do not show initials or names on open-group cards, the map or the projector.
- Do not build the desktop finder or badge screens from this plan.
- Do not rebuild the frontend. The changes above are incremental.

## 6. Open items I could not verify

- Figma frames themselves (no access).
- Onboarding steps 2 and 3, Study mode, forming-group card, paused banner and
  error states, dark mode, as rendered.
- Real camera scanning, live Gemini parsing, persistence after reload.
- Whether visibility settings change matching, beyond what the handoff says.
