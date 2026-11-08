# Hangout integration handoff

- Snapshot date: 2026-11-07 (America/Vancouver)
- Working branch: `feat/integrate`
- Application snapshot: `3254815 Add HTTPS sharing and harden group check-in`
- Base branch at snapshot: `main` and `origin/main` at `33a791a`
- Worktree before this document: clean

This is the standalone handoff for continuing this integration in Codex or
Claude. It describes what is actually in `feat/integrate`, what has and has not
been verified, and why the branch should not be merged into `main` yet.

Do not treat `docs/integration-notes.md` as a description of the current code.
That file is the phase-1, pre-implementation audit. It is useful for explaining
why changes were made, but many endpoints listed there as missing now exist.

The other files under `docs/` are intentionally excluded by this checkout's
`.git/info/exclude`. Only this handoff is force-added to Git. Do not accidentally
stage the whole directory, and do not copy credentials or `.env` values into a
commit.

## 1. Current Git state and history

`feat/integrate` is 15 commits ahead of `main`. The branch contains the original
three-page frontend, map, signup work, integration merges, and three main
backend/frontend integration commits.

| Commit | What it contributed |
| --- | --- |
| `33b565b` | Initial Right now, Map, and Me page boilerplate. |
| `77021a2` | Leaflet campus map, bounded panning, local geolocation, map tiles. |
| `e738239` through `c6f7626` | Guest/Auth0 signup, onboarding, route gate, and Auth0 diagnostics. |
| `c1e272d` | Later signup/Vite work from the login worktree. |
| `bf47e4a`, `9d7f6b4`, `6bec1ad` | Integrated login/signup and map work into `feat/integrate`. |
| `b32a3ae` | Updated environment guidance; the local agent documents created around this point remain excluded from Git. |
| `5b055fe` | Brought the backend toward the group, privacy, map, projector, reset, and check-in contracts. |
| `d9d9683` | Connected the pages through `src/lib/api.js`, fixed onboarding catalogs and start-group building slugs, and added QR/check-in UI. |
| `3254815` | Added temporary HTTPS sharing and improved camera/check-in diagnostics and typed-code UX. |

At this snapshot, no integration commit has been pushed to `main`. Keep it that
way until the backend lifecycle work described in section 8 is reconciled and
the complete phone demo passes.

## 2. Work completed

### Phase 1: audit

The original backend, database schema, signup work, and map work were audited
against `docs/AGENTS.md`, `docs/build-plan.md`, and `docs/SIGNUP.md`. The result
is in `docs/integration-notes.md`. It records the pre-change endpoint inventory,
schema mismatches, privacy breaks, obsolete building-QR/open-table/UBC-email
ideas, and the smallest integration plan.

Again, that audit is historical. This document is the current-state source.

### Backend alignment (`5b055fe`)

- Added one shared `MIN_GROUP_SIZE = 3` and `MAX_GROUP_SIZE = 5` in
  `backend/app/constants.py` and made matching/group views use them.
- Added `backend/sql/002_plan_alignment.sql`. It maps group states to
  `forming`, `confirmed`, `active`, `completed`, and `dissolved`; maps member
  responses to `invited`, `joined`, `declined`, and `expired`; drops the
  obsolete building QR secret; and adds `student_spots` for favourite spots.
- Kept `group_members.arrived_at` as attendance evidence. A checked-in member
  remains joined; API state `checked_in` is derived from `arrived_at`.
- Added the missing group, map, projector, check-in, profile-update, and demo
  reset behavior listed in section 4.
- Added signed check-in codes in `backend/app/codes.py`. Their payload is
  `hc1.<student_id>.<30-second-window>.<HMAC>`. Verification accepts the current
  and immediately previous window to tolerate a code expiring during a scan.
- Added privacy-aware group serialization in `backend/app/groups_view.py`:
  spots stay hidden while forming, invited people are counted but not named,
  and first names appear only for joined members to joined callers.
- Mirrored profile changes into the Supabase student row read by matching so
  pause and visibility are not merely in-memory UI settings.
- Added an actual demo reseed path and anonymous projector/map aggregation.
- Preserved compatibility reads/writes for parts of the original V1 schema
  (`proposed`, `pending`, and `skipped`) so application deployment and the
  plan-alignment migration did not have to be perfectly simultaneous.

### Frontend integration (`d9d9683`)

- Made `frontend/src/lib/api.js` the only frontend backend caller. It strips a
  trailing API base slash, uses `/api` through Vite by default, and turns
  FastAPI `detail` strings into user-facing errors.
- Guest sessions use `localStorage` key `hangout.session` and the same
  `Authorization: Bearer` header as Auth0 access tokens. Cookies are not used.
- A 401 clears only the guest session and emits the route-gate expiry event.
- Vite now proxies `/api/*` to FastAPI on port 8000 and strips `/api`.
  `BACKEND_URL` or `BACKEND_PORT` can override the development target.
- Fixture mode is opt-in with `VITE_USE_FIXTURES=true`; real API mode is the
  default.
- Onboarding reads canonical languages, tags, and building slugs from
  `GET /options`, with local data only as an offline fallback.
- Draft tag aliases were normalized (`first-year` to `first-term`, `grad` to
  `graduate`) before catalog validation. This fixed saved selections being
  silently discarded when an older draft used the previous slugs.
- Start-group building choices now come from the backend catalog and submit
  its canonical slug. This addressed hardcoded choices such as `ikb` not
  matching the database and made The Nest use the same path as every building.
- Right now now loads the suggestion, open groups, and building catalog; can
  join, skip, start a group for a gap or now; and mounts the code/scanner only
  for joined or checked-in members.
- Map now calls `GET /map`, renders anonymous building activity, and highlights
  the caller's returned meeting building.
- Me now loads the private profile and updates pause and visibility through
  `PATCH /me`; logout clears the guest session.
- Projector reads the backend's anonymous totals and dots.
- Loading, empty, error, and retry states were added around the three pages'
  API-backed sections.

### HTTPS and check-in usability (`3254815`)

- Added executable `scripts/share-demo.sh`. It starts or reuses FastAPI on
  `127.0.0.1:8000` and Vite on `127.0.0.1:5173`, then opens a temporary
  Cloudflare Quick Tunnel to Vite. Vite continues proxying `/api` to FastAPI,
  so teammates use one HTTPS origin.
- The script rewrites only the origin Host header instead of opening Vite's
  allowed-host configuration to every hostname. It leaves IDE servers it
  reused running when the tunnel stops.
- Added README instructions explaining that camera/geolocation APIs require
  HTTPS on teammate phones, that the URL is temporary/public to anyone who has
  it, and that Ctrl+C stops the tunnel.
- The scanner now reports insecure origin, denied permission, missing camera,
  and busy camera separately. It requests the rear-facing camera where
  available and mounts the video element before assigning the stream.
- Added typed-code input hardening, a full-code copy button, and clearer
  guidance that two distinct joined members are required.
- Submitting one's own code now returns
  `422 Use a groupmate's code, not your own.` Other invalid signatures,
  expired codes, and outside-group codes intentionally retain the same generic
  `422 That code is not valid.` response.

## 3. Runtime architecture and configuration

### Identity split that still exists

Identity is still split between two stores:

- `backend/app/store.py` is process-local and supplies the authenticated
  onboarding/profile object used by `GET /me` and several dependencies.
- Supabase stores matchable students, free blocks, groups, memberships,
  buildings, reference catalogs, and mirrored profile fields.

This is demo-grade, not durable architecture. Restarting the backend loses the
in-memory guest profiles even though related Supabase rows may remain, and
multiple uvicorn workers would not share the same in-memory identities. Do not
try to hide this in the handoff or assume a shared backend change preserves it.

### Environment rules

- The backend loads the repository-root `.env` and needs `SUPABASE_URL` and
  `SUPABASE_SERVICE_KEY` for database-backed endpoints.
- `GUEST_TOKEN_SECRET` is preferred, with `GUEST_SESSION_SECRET` supported as
  a compatibility name. The same value signs guest tokens and check-in codes.
  If both are absent, a random per-process value invalidates tokens/codes after
  a restart.
- `DEMO_MODE=true` enables guest creation and `POST /admin/reset`.
- Frontend-only public variables belong under `frontend/.env.local`, not the
  root `.env`. Never expose a Supabase service key or signing secret through a
  `VITE_*` variable.
- `VITE_API_URL` is optional in development because the Vite `/api` proxy is
  the default. `VITE_USE_FIXTURES` defaults to false.
- `VITE_STADIA_API_KEY` is optional. Without it, deployed/tunnel builds use
  OpenStreetMap's light tiles; Stadia without a deployed-domain key would 401.

## 4. Current HTTP contract

Private routes require `Authorization: Bearer <Auth0-or-guest-token>`. Public
routes are noted explicitly. The browser calls these through `/api` in local
Vite development; FastAPI itself exposes the paths below without that prefix.

| Method and path | Current request and response |
| --- | --- |
| `GET /health` | Public. Returns `{status: "ok"}`. |
| `GET /me` | Returns `{onboarded: false}` or `{onboarded: true, student}`. Private `student` has `id`, `first_name`, `is_guest`, `paused`, `visibility`, `tags`, and `favourite_spots`. |
| `POST /students` | Accepts name, exactly one of `preset_id`/`free_blocks`, tags, languages, courses, optional bio/spots/visibility, and `guest`. Returns `{student, aha, guest_token}`. |
| `PATCH /me` | Partial update for name, tags, languages, bio, visibility, favourite spots, and paused. Returns the private student. |
| `POST /me/paused` | Compatibility alias accepting `{paused}`. |
| `GET /auth/config` | Setup diagnostic: demo mode and Auth0 readiness, without secrets. |
| `GET /options` | Returns canonical `{languages, tags, buildings}`, each as `{id, label}`. Building IDs here are slugs accepted by `POST /groups`. |
| `GET /me/now` | Returns `{gap, group}`; either may be null. `group` is the `GroupOut` shape below. |
| `POST /groups/{id}/join` | Joins an invited/open group. Returns `{group_id, response: "joined"}`. |
| `POST /groups/{id}/skip` | Declines an invitation. Returns `{group_id, response: "skipped"}` at the compatibility HTTP boundary while storing `declined`. |
| `GET /groups/open` | Returns anonymous confirmed groups overlapping the caller's gaps, with gap, mode, general area, seats left, and shared signals—no names or exact spot. |
| `POST /groups` | Accepts `{building: <slug>, mode, now}` and returns the created `GroupOut`. Founder starts joined. |
| `GET /groups/{id}` | Member-only `GroupOut`; a non-member gets 404 so existence is not disclosed. |
| `GET /groups/{id}/checkin-code` | Joined member only. Returns `{code, expires_in}`. |
| `POST /groups/{id}/checkin` | Accepts `{code}`. Returns `{joined_count, checked_in_count, my_state, counted}` and attempts to mark both members arrived. |
| `GET /map` | Returns `{buildings: [{slug,name,lat,lng,free_count}], my_group}`. `my_group` has group/building identity, coordinates, and joined/check-in counts or is null. |
| `GET /projector` | Public. Returns `{forming, confirmed, checked_in, students, dots}`; dots are anonymous building clusters. |
| `POST /admin/reset` | Demo mode only. Reseeds demo data and returns seeded counts. |

`GroupOut` currently contains:

```json
{
  "id": "g_41",
  "state": "forming|confirmed|active|completed|dissolved",
  "mode": "social|study",
  "members": ["joined members' first names only"],
  "shared": ["shared signals"],
  "spot": {"building": "The Nest", "walk_min": 5},
  "joined_count": 3,
  "checked_in_count": 0,
  "seats_left": 2,
  "my_state": "invited|joined|declined|expired|checked_in",
  "needs": 0
}
```

`spot` is null while forming. The walk time is an explicit placeholder until
the data model has real walking distances.

## 5. Current database vocabulary

The integration branch assumes `backend/sql/001_core_schema.sql` followed by
`backend/sql/002_plan_alignment.sql`:

- `groups.status`: `forming`, `confirmed`, `active`, `completed`, `dissolved`.
- `group_members.response`: `invited`, `joined`, `declined`, `expired`.
- `group_members.arrived_at`: independent check-in timestamp; API member state
  becomes `checked_in` when a joined row has this value.
- `student_spots`: ranked favourite building rows.
- `buildings.code_secret`: removed because building QR codes were removed from
  the product.

Some repository methods deliberately fall back to the V1 values `proposed`,
`pending`, and `skipped`. That compatibility is not support for the incoming
`invitation_status` schema described later.

Before any further migration is applied, ask the backend teammate exactly
which SQL migrations have already been run against the shared Supabase project.
Git history alone cannot answer that question.

## 6. Privacy behavior already implemented

- Open groups, map data, and projector data contain no student names.
- Group first names are visible only to a joined caller and only for people
  who have joined; invitations do not disclose names.
- Forming groups do not serialize their meeting spot.
- Map building counts below `MIN_GROUP_SIZE` are omitted, not rounded or sent
  as a hidden frontend value.
- The browser uses a single local geolocation fix only to center/bound Leaflet.
  No coordinate is accepted by `GET /map` or sent to the backend.
- Non-members receive 404 from group detail rather than confirmation that the
  group exists.
- Pause is mirrored to the Supabase row read by matching.
- Check-in errors do not distinguish an expired signature from a forged or
  outside-group signature.

## 7. Known implementation issues — record now, do not fix before backend merge

### QR/check-in does not yet work reliably in the live demo

The feature is not absent: QR generation, camera decoding, typed fallback,
API calls, HMAC validation, and `arrived_at` writes all exist. The fake-database
contract tests prove the intended algorithm, including idempotency. They do not
prove that the configured Supabase schema and live membership values match it.

Required conditions for the current implementation are strict:

1. Two distinct profiles/tokens must be used; using one's own code is rejected.
2. Both profiles must be memberships of the same group.
3. Both membership rows must have `response = "joined"`.
4. The displayed `hc1...` code must be current and generated by a process using
   the same signing secret as the process validating it.
5. The phone opening the camera must use the HTTPS tunnel, not a LAN HTTP URL.

`GroupMemberRepository.mark_arrived()` silently skips a membership whose
`response` is not exactly `joined`. This is the first seam to revisit after the
lifecycle branch lands. The current endpoint also performs two row updates
rather than one transaction; partial failure is possible and should be assessed
against the teammate's transaction/RPC approach.

The correct future acceptance test is not another fake-only unit test. Use two
separate phone/browser sessions against a disposable or agreed shared Supabase
database, join the same confirmed group, scan in both directions, and verify
both rows' timestamps plus the Right now, map, and projector counts.

### Map appears empty or does not show the expected group

An empty activity list can be valid under the current privacy rules. `GET /map`:

- reads only groups dated today;
- omits a public building until at least three distinct live members are there;
- requires a valid seeded building row with coordinates;
- returns the caller's meeting pin only when `state_for(...)` equals exactly
  `confirmed`.

That last condition is a concrete likely defect: an already `active` group has
a revealed meeting spot elsewhere in the UI but currently fails the exact
`confirmed` comparison and receives no `my_group` pin. Revisit this after the
teammate lifecycle states are authoritative.

The tile layer itself is separate from backend activity. It uses Stadia only
when allowed and otherwise OpenStreetMap. Approximate coordinates in
`frontend/src/lib/mapConfig.js` and fixtures are explicitly unverified; the
database building rows returned by `/map` are the runtime source of pin
coordinates. A future diagnosis should separately test: tile loading, `/map`
response data, group-state eligibility, seeded coordinates, and Leaflet render.

### Start-group and onboarding fixes need regression coverage after catalogs change

The UI now submits building slugs returned by `GET /options`, rather than a
hardcoded dropdown. If a teammate changes the options response or building
schema, preserve that single catalog source; do not restore a separate frontend
list. Likewise, preserve canonical tag IDs and the old-draft aliases when the
signup backend changes.

## 8. Incoming teammate backend: do not merge blindly

The latest fetched backend work is `origin/feat/group-lifecycle` at `c77ad3f`
(with earlier commit `181d748`). `origin/main` has not moved from `33a791a`.

It overlaps this branch in eleven important files:

```text
README.md
backend/app/matching.py
backend/app/repositories/base.py
backend/app/repositories/group_members.py
backend/app/repositories/groups.py
backend/app/routers/groups.py
backend/app/routers/students.py
backend/tests/fakes.py
backend/tests/test_api_contracts.py
backend/tests/test_matching.py
backend/tests/test_security_and_errors.py
```

The overlap is semantic, not just textual:

- This branch stores `group_members.response` with `joined`; the teammate
  branch renames the column to `invitation_status` and uses `accepted`.
- This branch has `002_plan_alignment.sql`; the teammate branch independently
  has `002_group_lifecycle.sql`.
- The teammate migration adds `invite_expires_at`, `confirmed_at`, and
  `status_changed_at`, plus an atomic invitation-response RPC.
- The teammate code adds invitation deadlines, expiry/dissolution behavior,
  time-driven active/completed transitions, and separate attendance derivation.
- Both branches implement confirmation/member counting and repository methods,
  so accepting either entire side during a conflict would discard required
  behavior from the other.

First determine what has been applied to Supabase. Then adopt the teammate
backend's lifecycle/storage naming as the durable backend model, because the
project contract says the pushed backend wins on naming. Adapt the existing
frontend-facing API to that model so the pages do not need to learn database
column names. Preserve from this branch: privacy serialization, map count
hiding, check-in HMAC/API semantics, frontend response shapes, canonical
catalogs, and demo behavior.

Do not apply both `002` migrations in arbitrary order. Produce one reconciled,
ordered migration path based on actual database state and test it on a disposable
database before the shared project.

## 9. Verification already completed

Current application snapshot verification:

- Backend: 56 tests passed; one optional live Supabase integration test skipped.
- Frontend: ESLint passed and the Vite production build completed (134 modules).
- Tunnel smoke test: a real temporary Cloudflare HTTPS URL returned 200 for `/`
  and for proxied `/api/health`.
- Shell syntax and Git whitespace checks passed for the HTTPS script/change.

Run the backend suite from `backend/`, not the repository root, because imports
expect `backend` to be the working directory:

```bash
cd backend
.venv/bin/python -m unittest discover -s tests -v
```

The live Supabase test is intentionally skipped unless explicitly enabled; the
passing 56-test result is therefore not evidence that QR or map works against
the shared database.

Frontend checks:

```bash
cd frontend
npm run lint
npm run build
```

HTTPS teammate demo from the repository root:

```bash
./scripts/share-demo.sh
```

Share the printed `https://*.trycloudflare.com` URL and keep the terminal open.

## 10. Recommended continuation order

1. Wait until the backend teammate says the lifecycle branch is ready.
2. Fetch it and re-check its head; do not assume `c77ad3f` remains final.
3. Ask which migrations have been applied to the shared Supabase project.
4. Integrate the lifecycle/storage model into `feat/integrate`, resolving the
   eleven overlaps deliberately and preserving both sides' working behavior.
5. Reconcile the migrations before changing QR or map adapters.
6. Update group serializers, check-in writes, and map state eligibility to the
   final lifecycle vocabulary while keeping the frontend HTTP shapes stable.
7. Run the automated suites and a disposable-database migration/integration
   pass.
8. Run the full `docs/AGENTS.md` demo on HTTPS at a 390px phone viewport,
   including two distinct guests checking each other in and map/projector count
   updates.
9. Merge to `main` only when the demo spine passes end to end.

Until then, do not merge or push this integration branch to `main` merely
because its unit tests and build pass. The known live-data seams are the core
product path, not optional polish.
