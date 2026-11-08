# Hangout integration handoff

- Snapshot date: 2026-11-07 (America/Vancouver), revised the same day
  after the lifecycle merge
- Working branch: `feat/integrate`
- Application snapshot: the lifecycle merge described in section 8
- Base branch at snapshot: `origin/main` at `04c0f46`
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

`backend/sql/schema.sql` is the one schema file, and there are no migrations.
The lifecycle branch replaced `001_core_schema.sql` and its own
`002_group_lifecycle.sql` with a single canonical file for a fresh Supabase
project, and the integration branch's `002_plan_alignment.sql` was deleted
during the merge rather than carried forward. It had become a trap: it rewrote
`group_members.response`, a column the canonical schema no longer has, and
dropped `buildings.code_secret`, which the canonical schema requires. Running
it against a current database would fail partway through.

The vocabulary the code now reads and writes:

- `groups.status`: `forming`, `confirmed`, `active`, `completed`, `dissolved`.
- `groups.invite_expires_at`, `confirmed_at`, `status_changed_at`: the
  lifecycle columns. `invite_expires_at` is NOT NULL and constrained to fall
  before the meeting starts; `GroupRepository.create` sets it to ten minutes
  before the start time.
- `group_members.invitation_status`: `invited`, `accepted`, `declined`,
  `expired`. This is the durable name and `accepted` is the durable value.
- `group_members.arrived_at`: check-in timestamp, constrained to accepted
  rows only. API member state becomes `checked_in` when an accepted row has
  one.
- `buildings.code_secret`: still present and NOT NULL. Nothing reads it. It
  belonged to the building-QR idea the product dropped, and `app/demo.py`
  seeds an inert `obsolete-<slug>` value so an insert can satisfy the
  constraint without reviving the column's meaning.
- `student_spots`: does not exist. Favourite spots live only in
  `app/store.py`, alongside the rest of the split identity.

`normalize_membership()` in `app/repositories/group_members.py` is the seam
between the two vocabularies. Storage keeps `invitation_status`/`accepted`;
every row read through the repository also carries the wire name `response`
with the value `joined`, which is what the view layer and the three pages
use. Nothing above the repository should read `invitation_status` directly.

Some repository methods still fall back to the V1 values `proposed`,
`pending`, and `skipped`, for a database seeded before the lifecycle schema.

A fresh project is installed from `schema.sql` alone. For a database that
already holds data, ask the backend teammate what has been applied; Git
history cannot answer that.

## 6. Privacy behavior already implemented

- Open groups, map data, and projector data contain no student names.
- Group first names are visible only to a joined caller and only for people
  who have joined; invitations do not disclose names.
- The meeting spot is serialized only to a caller who has joined, and only
  once the group is past forming. Both halves are required, and one
  function, `spot_is_visible_to()`, is the only place they are decided.
- Map building counts below `MIN_GROUP_SIZE` are omitted, not rounded or sent
  as a hidden frontend value.
- The browser uses a single local geolocation fix only to center/bound Leaflet.
  No coordinate is accepted by `GET /map` or sent to the backend.
- Non-members receive 404 from group detail rather than confirmation that the
  group exists.
- Pause is mirrored to the Supabase row read by matching.
- Check-in errors do not distinguish an expired signature from a forged or
  outside-group signature.

## 7. Known implementation issues still open

### QR/check-in does not yet work reliably in the live demo

The feature is not absent: QR generation, camera decoding, typed fallback,
API calls, HMAC validation, and `arrived_at` writes all exist. The fake-database
contract tests prove the intended algorithm, including idempotency. They do not
prove that the configured Supabase schema and live membership values match it.

Required conditions for the current implementation are strict:

1. Two distinct profiles/tokens must be used; using one's own code is rejected.
2. Both profiles must be memberships of the same group.
3. Both membership rows must have `invitation_status = "accepted"`.
4. The displayed `hc1...` code must be current and generated by a process using
   the same signing secret as the process validating it.
5. The phone opening the camera must use the HTTPS tunnel, not a LAN HTTP URL.

`GroupMemberRepository.mark_arrived()` silently skips a membership that is
not accepted, and `schema.sql` now enforces the same thing as a check
constraint, so a check-in against a non-accepted row cannot half-succeed at
the database either. The endpoint still performs two row updates rather than
one transaction, so a partial failure remains possible. The lifecycle branch
brought an atomic RPC for invitation responses; check-in has no equivalent yet
and is the obvious next candidate for one.

The correct future acceptance test is not another fake-only unit test. Use two
separate phone/browser sessions against a disposable or agreed shared Supabase
database, join the same confirmed group, scan in both directions, and verify
both rows' timestamps plus the Right now, map, and projector counts.

### Map appears empty or does not show the expected group

An empty activity list can be valid under the current privacy rules. `GET /map`:

- reads only groups dated today;
- omits a public building until at least three distinct live members are there;
- requires a valid seeded building row with coordinates;
- returns the caller's meeting pin only when that caller has joined the group
  and the group is confirmed, active or completed.

The two defects this section used to predict are fixed, with tests: the pin no
longer disappears when a group becomes `active`, and it is no longer handed to
a caller who has only been invited. See section 8.

The tile layer itself is separate from backend activity. It uses Stadia only
when allowed and otherwise OpenStreetMap. Approximate coordinates in
`frontend/src/lib/mapConfig.js` and fixtures are explicitly unverified; the
database building rows returned by `/map` are the runtime source of pin
coordinates. A diagnosis should separately test: tile loading, `/map` response
data, group-state eligibility, seeded coordinates, and Leaflet render.

### Start-group and onboarding fixes need regression coverage after catalogs change

The UI now submits building slugs returned by `GET /options`, rather than a
hardcoded dropdown. If a teammate changes the options response or building
schema, preserve that single catalog source; do not restore a separate frontend
list. Likewise, preserve canonical tag IDs and the old-draft aliases when the
signup backend changes.

## 8. Teammate backend lifecycle merge: done

`origin/main` reached `04c0f46` (pull request #14, `feat/group-lifecycle`) and
is merged into `feat/integrate`. The eleven overlapping files were resolved
deliberately rather than by taking a side. The rule applied throughout: the
pushed backend wins on storage and lifecycle naming, this branch wins on the
HTTP shapes the three pages already consume, and the adapter between them is
`normalize_membership()`.

What that meant in practice:

- `group_members.invitation_status` with `accepted` is the stored truth. The
  wire keeps `response: "joined"`, `state`, `my_state`, `joined_count` and
  `needs`, so no page had to learn a database column name.
- `GET /me/now` keeps answering with the `{gap, group}` pair. The lifecycle
  branch's `{"status": "waiting"}` shape was not adopted.
- Invitation deadlines, expiry, dissolution and the time-driven
  active/completed transitions come from the teammate's `app/lifecycle.py`
  and the atomic invitation-response RPC.
- The privacy serialization, map count hiding, check-in HMAC semantics,
  canonical catalogs and demo reseed were all kept from this branch.

Three defects were found and fixed while reconciling, each with a test that
fails without the fix:

- **An invited caller could see the meeting spot.** `group_out` gated the
  spot on the group's state alone, so a member who had not accepted still
  received the building name on a confirmed group. The spot now needs the
  caller to have joined as well. The teammate's
  `test_remaining_invited_member_cannot_see_names_or_location` is what
  surfaced this; it was failing for a different reason and the real bug was
  behind it.
- **`GET /map` leaked the same thing, with coordinates.** Its `my_group` pin
  checked only that a membership row existed, not that it was accepted.
- **`GET /map` dropped the pin when the meeting started.** The eligibility
  test was an exact comparison against `confirmed`, so an `active` group got
  no pin at the one moment its members need directions. This was predicted
  in an earlier draft of this document and is now fixed.

All three now go through one predicate, `spot_is_visible_to()` in
`app/groups_view.py`, so the three routes that answer "may this caller learn
where the group is meeting" cannot drift apart again.

`backend/tests/test_lifecycle_api.py` arrived with the lifecycle branch and
needed adapting, not weakening. It seeded students into the Supabase fake
only, but a guest token on this branch verifies against `app/store.py`, so
every private route answered 401. Its `setUp` now mirrors the seeded students
into the store, which is what `POST /students` does in production. Its
assertions were renamed to this branch's wire vocabulary; every condition it
checked is still checked.

One feature was deliberately not carried over: `GroupOut` does not expose
`invite_expires_at`, so the UI cannot yet show a "respond by" deadline even
though the backend enforces one. Adding it is an API contract change and is
left here rather than made quietly.

## 9. Verification already completed

Current application snapshot verification:

- Backend: 100 tests passed, 6 skipped. The skips are the optional live
  Supabase integration tests.
- Frontend: ESLint passed and the Vite production build completed (134
  modules), with the Leaflet chunk still split out at ~158 kB.
- `npm run check:signup` passed all 17 route-gate checks.
- Server-side render of `/`, `/map`, `/me` and `/projector` all succeeded
  with no Leaflet in the output, so the lazy map import survived the merge.
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
passing 100-test result is therefore not evidence that QR or map works
against the shared database. Every test above runs against the in-process
fake.

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

Steps 1 to 6 of the previous version of this list are done; see section 8.
What is left:

1. Ask the backend teammate whether the shared Supabase project has been
   reinstalled from `sql/schema.sql`. Everything below assumes it has. Git
   history cannot answer this.
2. Install `sql/schema.sql` on a disposable project and run the live
   integration tests against it, with `RUN_SUPABASE_INTEGRATION=1` and the
   two confirmation variables in `.env.example`. This is the first real
   evidence that the merged code and the schema agree.
3. Run the full `docs/AGENTS.md` demo over HTTPS at a 390px phone viewport:
   two distinct guests, the same confirmed group, a check-in scanned in both
   directions, and the Right now, map and projector counts all moving.
4. Verify the UBC coordinates in `frontend/src/lib/mapConfig.js` and in the
   seeded `buildings` rows against a real map. They are all still
   approximate and unverified, and the map is a judged surface.
5. Send `courses` from `createStudent` in `frontend/src/lib/api.js`. The
   backend accepts and validates the field, so shared-course matching has no
   data until onboarding collects it, and "you both take STAT 302" is the
   strongest line on a group card.
6. Decide whether `GroupOut` should carry `invite_expires_at`. The backend
   enforces the deadline; the UI cannot show it.
7. Retire the split identity by moving `app/store.py` into Supabase. The
   columns already exist. This is the largest piece of demo-grade debt on the
   branch, and it is what makes a backend restart lose guest profiles.
8. Merge to `main` only when step 3 passes end to end.

Until then, do not merge or push this integration branch to `main` merely
because its unit tests and build pass. The known live-data seams are the core
product path, not optional polish.
