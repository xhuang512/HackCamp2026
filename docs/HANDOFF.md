# Hangout handoff

- Snapshot: 2026-11-08 (America/Vancouver), after the schedule merge and the
  Figma design pass
- Working branch: **`feat/figma-design`** at `8b1a0a7`, not pushed
- Worktree at snapshot: clean
- **This checkout is what `ubcmeet.fit` serves.** See section 3.

Standalone handoff for continuing in Codex or Claude. It describes what is in
the branch, what is verified, what is not, and the one thing blocking a demo.

Two older documents are history, not current state. `docs/integration-notes.md`
is a pre-implementation audit from 2026-11-07. `docs/integration-report.md` is
the phase-1 audit from the schedule pass. Both explain why things were done;
neither describes the code now. This file does.

`docs/` is excluded in `.git/info/exclude`. Only `HANDOFF.md`,
`design-report.md` and `integration-report.md` are force-added. Do not stage
the whole directory and never put `.env` values in a commit.

## 1. Read this first

**The shared Supabase project is on the old schema, so the demo cannot run.**
Every groups read returns 502 through the domain while the site looks healthy:

```
$ curl -s https://api.ubcmeet.fit/projector
error code: 502
$ curl -s https://api.ubcmeet.fit/health
{"status":"ok"}
```

Missing: `groups.invite_expires_at`, `confirmed_at`, `status_changed_at`,
`group_members.invitation_status`, the `respond_to_group_invitation` function,
and `student_spots`. Right now, Map and Projector are the whole demo spine and
all three are down. The measured delta and two ways to apply it are in
`docs/schema-gap.md`, **which is on disk but untracked**, so force-add it if
the handoff needs to travel.

The user has chosen to hold off on applying it. Nothing else in this document
is worth doing before it.

## 2. Where the work is

| Branch | Worktree | State |
| --- | --- | --- |
| **`feat/figma-design`** | this checkout | `8b1a0a7`, 10 ahead of `feat/integrate`, **not pushed** |
| `feat/integrate` | shared | `80111ee`, 28 ahead of `main`, 2 ahead of its remote |
| `feat/deploy` | `../HackCamp2026-deploy` | `fb75383`, owned by the deploy session |
| `log-in`, `feat/map-page` | separate worktrees | older, already merged in |
| `main` | | 6 behind `origin/main`; nothing from this session is on it |

`feat/figma-design` contains everything: the three-page frontend, map, signup,
the lifecycle merge, the schedule merge, and the design pass. It is the only
branch to work from.

Another Claude session owns `feat/deploy` and the serving layer. Coordinate
before touching `deploy/`, ports 8000 and 4173, or the launchd agents.

## 3. This branch is live, and nothing reloads

Three launchd agents run with `--serve-from` pointed at this checkout:

| Agent | What |
| --- | --- |
| `fit.ubcmeet.backend` | `uvicorn app.main:app` on `127.0.0.1:8000`, no `--reload` |
| `fit.ubcmeet.frontend` | `vite preview` on `127.0.0.1:4173`, serving `frontend/dist` |
| `fit.ubcmeet.tunnel` | Cloudflare tunnel to `ubcmeet.fit` |

So `uvicorn` runs this branch's Python directly and `vite preview` serves this
tree's `frontend/dist`. No merge is involved and `feat/integrate` and `main`
are not in the path. **Every commit here is one restart from being public.**

```bash
cd ../HackCamp2026-deploy && ./deploy/install.sh --serve-from ~/Documents/Files/Code/HackCamp2026
# or one service:
launchctl kickstart -k "gui/$(id -u)/fit.ubcmeet.frontend"
```

Both processes were once stale by six commits with no visible symptom, because
every endpoint still answered. Do not use "the site is up" as evidence that
your change shipped. Check the bundle hash or the OpenAPI schema.

## 4. What this session did

### Pass one, the schedule backend merge

`origin/main` gained `90b7438`, the Gemini schedule work. Merged in `7d77417`.
Two conflicts, both import unions. Seven of the teammate's new tests returned
401 for the same reason the lifecycle tests did: `ScheduleApiTests` seeded
neither half of the split identity, so a guest token verified against nothing.
Fixed in the test by writing the store half in `setUp`, the way
`POST /students` does, with `store.reset()` in `tearDown`. The auth was not
weakened.

Two new endpoints arrived and **neither is wired to any screen**:

| Endpoint | State |
| --- | --- |
| `POST /schedule/parse` | Returns 503 today. No `GOOGLE_CLOUD_GEMINI_API_KEY` is set anywhere. |
| `PUT /me/schedule` | Works, but see the split-store bug below. |

The phase-1 audit for that pass is `docs/integration-report.md`, including a
thirteen-item "For the backend owner" list. Phases 2 to 4 were never run,
because the design work was started instead.

### Pass two, the Figma design

Eight commits, `c626166` through `c7a5fbd`, plus two correction commits. Full
record in `docs/design-report.md`, including the frame map, the token table
and a "For the designers" list.

| Commit | Screen |
| --- | --- |
| `c626166` | Tokens and fonts |
| `893d35f` | Welcome |
| `a2c7abd` | Right now |
| `2e577cb` | Check-in, plus the six-digit code |
| `9c99544` | Map |
| `89ec1d2` | Me and Settings |
| `16ea145` | Onboarding |
| `c7a5fbd`, `06781a3`, `8b1a0a7` | Report and corrections |

Figma file: `rIG6FVvppwm5Yd2Evpf0Dv`, page **Hackercamp (IDEAS)**. It is a
duplicate the user owns; the original was view-only and Figma's MCP server
refuses every tool, including reads, without edit access.

The largest single change was not a colour. **Inter was named in `tokens.css`
and never loaded**, so every screen had been rendering in the system fallback.
It is now self-hosted through `@fontsource-variable/inter`, not Google Fonts,
so the stage demo does not depend on venue wifi reaching `fonts.gstatic.com`.

The palette already matched, because `tokens.css` and the Figma file were both
built from the UBC colours. Only four token deltas were needed.

## 5. The one contract change, and why

`GET /groups/{id}/checkin-code` now returns `typed` beside `code`, and
`POST /groups/{id}/checkin` accepts either.

The typed fallback used to be the whole QR payload, about forty characters,
behind a disclosure. The user asked for something a person can read aloud, so
it is six digits.

- **The QR payload is byte-identical** and keeps its 64-bit signature. The
  path that matters is unchanged.
- The six digits are a **separate HMAC over a different payload**, not a slice
  of that signature, so reading one form off a screen reveals nothing about
  the other. A test asserts it.
- `read_typed()` takes its candidate students explicitly, because six digits
  name nobody. The route passes the group's own members, at most five people
  over two windows. That list is both the search space and the reason a code
  minted for one group cannot be spent in another.

Sized honestly: the endpoint needs a valid session **and** membership of the
group being guessed at, so an attacker is already inside it. Even odds cost
about 70,000 requests inside the 60 seconds a code stays acceptable, and the
prize is a false check-in for an existing groupmate, which inflates the
hangout metric rather than exposing anything.

**The rate limit is decided and is not backend work.** It goes in as a
Cloudflare rule, spec at `deploy/rate-limit.md` on `feat/deploy`. One thing to
protect: the rule is POST-only because `ends_with(/checkin)` also matches
`/checkin-code`, which every phone polls once per rotation. Drop the method
condition and the code display dies for the whole room at once.

`CheckInCode` polls with a chained `setTimeout` at `expires_in`, so it is one
request per rotation and cannot pile up. Keep it that way; do not turn it into
an interval.

## 6. Architecture that has not changed

### The split identity

Still two stores, still demo-grade:

- `backend/app/store.py` is process-local and holds the authenticated
  onboarding profile behind `GET /me` and most dependencies.
- Supabase holds matchable students, free blocks, groups, memberships,
  buildings, catalogs.

`POST /students` writes both. A backend restart loses in-memory guest profiles
while the Supabase rows survive, and multiple uvicorn workers would not share
identities. This is the largest piece of debt on the branch.

**It now has a live bug.** `PUT /me/schedule` writes only the Supabase
`free_blocks`. `GET /me/now` reads the suggested group from Supabase but takes
its gap label from `_next_gap(student)` in `routers/students.py`, which reads
`store.py`. So confirming a parsed schedule changes which groups you match
into and not the gap printed above them. Fix it by writing both halves, the
way `POST /students` already does.

### Database vocabulary

`backend/sql/schema.sql` is the one schema file and there are no migrations.
`normalize_membership()` in `app/repositories/group_members.py` is the seam:
storage keeps `invitation_status`/`accepted`, and every row read through the
repository also carries the wire name `response` with value `joined`. Nothing
above the repository should read `invitation_status` directly.

- `groups.status`: `forming`, `confirmed`, `active`, `completed`, `dissolved`
- `group_members.invitation_status`: `invited`, `accepted`, `declined`, `expired`
- `group_members.arrived_at`: check-in timestamp, accepted rows only
- `buildings.code_secret`: present, NOT NULL, read by nothing. `app/demo.py`
  seeds an inert `obsolete-<slug>`.
- `student_spots`: does not exist. Favourite spots live only in `store.py`,
  and `PATCH /me` accepts `favourite_spots` and silently discards them.

### Privacy behaviour, all still enforced

- Open groups, map data and projector data carry no names.
- First names reach a joined caller only, and only for people who have joined.
- The spot is serialized only to a caller who has joined, and only once the
  group is past forming. One function, `spot_is_visible_to()` in
  `app/groups_view.py`, decides this for all three routes so they cannot drift.
- Map counts below `MIN_GROUP_SIZE` are omitted server-side.
- The browser's geolocation fix only centres and bounds Leaflet. No coordinate
  reaches the backend.
- Non-members get 404 from group detail, not a 403 that confirms existence.
- Check-in errors do not distinguish expired from forged from outside-group.

Two design frames break these rules and were **not** built as drawn: initials
on open-group cards the reader has not joined, and an exact building and room
before joining. Both are recorded in `docs/design-report.md`.

## 7. What is verified, and what is not

Run from the right directory. The backend suite needs `backend/` as cwd.

```bash
cd backend && .venv/bin/python -m pytest -q
cd frontend && npm run lint && npm run build && npm run check:signup
```

| Check | Result at `8b1a0a7` |
| --- | --- |
| Backend | 116 passed, 7 skipped |
| Frontend lint | clean |
| Frontend build | clean, 139 modules, Leaflet split at 157.65 kB |
| `check:signup` | 17/17 |
| Contrast, both modes | 15 pairs resolved from the stylesheet, worst 4.89:1 |
| Touch targets | zero interactive elements under 44px on `/`, `/map`, `/me` |

**Every one of those runs against a fake or a desk.** The seven skips are the
live Supabase integration tests.

What is **not** verified, and cannot be until section 1 is fixed:

- The six-digit code has never been exchanged between two phones.
- Right now, Map and Projector have never rendered real data through the
  domain. They 502.
- The AGENTS.md demo check has never passed end to end.

Treat the check-in work as unit-verified and integration-unverified. Do not
let a green test run stand in for that.

## 8. Continuation order

1. **Apply `docs/schema-gap.md` to the shared Supabase project.** Nothing
   below works first. The user is holding off deliberately, so ask before
   doing it.
2. Run the live integration tests against it with `RUN_SUPABASE_INTEGRATION=1`
   and the two confirmation variables from `.env.example`.
3. Fix `PUT /me/schedule` writing only one half of the split identity
   (section 6). Small, and it makes the schedule feature honest.
4. Run the full AGENTS.md demo over HTTPS at 390px: two guests, one confirmed
   group, a check-in scanned both ways, and the Right now, Map and Projector
   counts all moving.
5. Enter the Cloudflare rate-limit rule from `deploy/rate-limit.md`.
6. Decide the product name. The frames and the domain say **UBC Meet**; the app
   says **Hangout** in `index.html`, the meta tags, the manifest and `Welcome`.
   Tab labels differ too: the frames say "Groups · Map · My profile", the app
   says "Right now · Map · Me". All copy, no logic.
7. Wire `POST /schedule/parse` and `PUT /me/schedule` into a review screen on
   `Me`. Needs `GOOGLE_CLOUD_GEMINI_API_KEY` set, and it returns 503 until
   then. Neither route can be reached during onboarding; both go through
   `onboarded_user` and 403 without a profile.
8. Verify the UBC coordinates in `frontend/src/lib/mapConfig.js` and the seeded
   `buildings` rows against a real map. Still approximate, and the map is a
   judged surface.
9. Retire the split identity by moving `store.py` into Supabase. The columns
   exist.
10. Merge to `main` only after step 4 passes.

Open backend items are in `docs/integration-report.md`. The largest is that
`app/lifecycle.py`'s `expire_invitations()` and `advance_group_for_time()`
have **no callers**, so invitations never expire and no group reaches
`active`, both of which AGENTS.md requires.

## 9. Rules worth not breaking

- `src/lib/api.js` is the only file that calls the backend. Keep it that way.
- `src/styles/tokens.css` is the only file that defines a colour. There are no
  hardcoded hex values in any component, and that was true before this session
  too.
- Dark mode is real and has no design source. Any new colour pair needs a dark
  partner and a contrast check in both modes.
- `--c-bg` and `--c-surface` are crossed in light mode and uncrossed in layer 4
  for dark, because a raised card has to stay lighter than its page. Do not
  "simplify" that.
- Leaflet is lazy-loaded behind `canUseDOM` plus `React.lazy` because it reads
  `window` at module scope. An SSR render of `/map` must stay clean.
- The 44px touch floor and 4.5:1 contrast are an entered award track, not
  preferences.
- Do not merge or push to `main` because unit tests and the build pass. The
  live-data seams are the core product path.
