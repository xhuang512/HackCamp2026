# Backend and frontend integration report

- Run date: 2026-11-07 (America/Vancouver)
- Branch: `feat/integrate`, level with `origin/main` at `04c0f46`, 17 commits ahead
- Marker tag `last-integration`: did not exist, so everything below is treated
  as new
- Method: endpoints read from the FastAPI app's own `/openapi.json`, generated
  in process so no port was taken; frontend calls read from
  `frontend/src/lib/api.js` and matched against it by path and method

## Headline

There are **no broken calls**. All sixteen paths `api.js` calls exist on the
backend with the shapes it expects, so phase 2 has nothing to do.

The gap is not missing endpoints, it is **unused data inside endpoints the
frontend already calls**. Four fields the backend returns or accepts are never
read or sent, and two of them carry the demo's strongest lines. Separately,
two screens never refresh, which is enough on its own to fail step 5 of the
AGENTS.md demo check.

## 1. Broken calls

None.

| Checked | Result |
| --- | --- |
| 16 frontend paths against 18 backend operations | every one resolves |
| Response shapes against `src/lib/fixtures.js` | no drift |
| Required response fields against component reads | no component reads a field the backend omits |

Two backend operations have no frontend caller, both deliberately:

- `POST /me/paused` is a compatibility alias. `api.setPaused()` goes through
  `PATCH /me` instead, which is the documented route. Leave it.
- `GET /auth/config` has no wrapper at all. See item 2.1.

One fixture does disagree with the backend's behaviour, which is a defect in
the fixture rather than a broken call. See item 5.2.

## 2. New or unused endpoints

| Endpoint | What it does | Belongs in | Tier |
| --- | --- | --- | --- |
| `GET /auth/config` | Reports the backend's real `DEMO_MODE`, whether the guest signing secret is set, and whether Auth0 is configured and reachable. No secrets, only set/unset. | `src/lib/authContext.js`, and the Welcome screen through it | Not in AGENTS.md (setup aid) |
| `POST /admin/reset` | Reseeds buildings, students and groups. Returns the three counts. `api.adminReset()` exists already. | Projector screen, demo mode only | **Tier 1**, item 6, and step 6 of the demo check |
| `GET /groups/{id}` | Full `GroupOut` for one group, members only. `api.getGroup()` exists already. | Nothing. The group card gets the same object from `GET /me/now`. | Tier 1 contract, already satisfied elsewhere |
| `GET /health` | `{status: "ok"}`. `api.getHealth()` exists already. | Nothing. Right Now already detects an unreachable backend from `error.status === 0`. | Not in AGENTS.md |

### 2.1 Why `GET /auth/config` is worth wiring

The frontend currently guesses demo mode from its own env var:

```js
// src/lib/authContext.js:29
import.meta.env.VITE_DEMO_MODE === 'true' || !auth0Configured
```

That is the frontend's opinion, not the backend's. When `VITE_DEMO_MODE=true`
and the backend's `DEMO_MODE` is off, the Welcome screen offers "Continue as
guest", the student taps it, and `POST /students` refuses to issue a guest
token. The button is a dead end and nothing explains why. `GET /auth/config`
is the authoritative answer and is public, so it can be read before sign-in.

## 3. Unused fields in endpoints the frontend already calls

This is where the real work is.

### 3.1 `mode` is returned everywhere and displayed nowhere — Tier 1

`GroupOut.mode` and `OpenGroupOut.mode` are both `social | study` and
required. Nothing renders either.

Worse than unused, Right Now derives the group card's heading from its own
local toggle:

```js
// src/pages/RightNow.jsx:56
const label = mode === 'social' ? 'Your group for this gap' : 'Your quiet study group'
```

`mode` here is `useState('social')`, not `data.group.mode`. A student whose
suggested group is a study group reads "Your group for this gap" until they
happen to flip the toggle. The file's own header comment says "Mode is local
for now", which was true when it was written and is not any more.

In the open groups list, a study group and a social group are visually
identical, so the one fact that decides whether a student wants to join is
the one fact missing.

### 3.2 `courses` is accepted and never sent — Tier 1

`CreateStudentRequest.courses` is a list of up to ten course codes.
`api.createStudent()` does not include the field in its body at all.

What it feeds, verified in the code rather than assumed:

- `StudentRepository.shared_signals()` reads `student_courses` and puts course
  codes **first** in the `shared` list, ahead of tags and languages. This is
  the "STAT 302" in AGENTS.md's own example response and the strongest line on
  a group card.
- It does **not** feed matching. `engine.form_groups()` says in its docstring
  that it "intentionally ignores matching signals" and groups purely on time
  overlap. So sending courses changes what a card *says*, not who is in it.

Codes are free text, normalised by `normalize_course_code()` to
`^([A-Z]{2,5})([0-9]{3}[A-Z]?)$` and rendered as `STAT 406`. Unknown codes are
created on demand, so no catalog is needed and `GET /options` deliberately
does not offer one.

One deployment catch: `POST /students` returns **422** if `courses` is
non-empty while the backend's `CURRENT_TERM` environment variable is unset
(`app/routers/identity.py:372`). Sending courses makes a previously working
signup fail on any backend missing that variable. `.env.example` lists
`CURRENT_TERM` but leaves it blank.

### 3.3 `PATCH /me` accepts seven fields and the Me screen sends two

| Field | Sent by Me screen? |
| --- | --- |
| `paused` | yes |
| `visibility` | yes |
| `first_name` | no |
| `tags` | no |
| `languages` | no |
| `ask_me_about` | no |
| `favourite_spots` | no |

`StudentOut` also returns `favourite_spots`, which no component reads.

Two asymmetries worth knowing before building anything here:

- `PATCH /me` accepts `languages` and `ask_me_about`, but `StudentOut` does
  not return either. They can be written and never read back.
- `favourite_spots` **cannot persist**. See item 4.2. Building the editor
  would produce a control that appears to work and silently forgets.

Editing name and tags is a plain win and depends on nothing. Favourite spots
is Tier 2 in AGENTS.md and is blocked on the backend.

### 3.4 Two screens never refresh — Tier 1, and it fails the demo check

Neither the Projector nor the Map polls or subscribes. `useAsync` fetches once
per mount and only refetches when something calls `reload()`. Nothing does on
either screen.

Step 5 of the AGENTS.md demo check is "Two phones in the same group check each
other in, and the projector's checked-in count goes up". It will not go up.
The number is correct at the moment the page loads and then frozen, so the
stage demo needs someone to reload the laptop by hand at the right second.

`src/lib/live.js` is the intended long-term answer and is an honest stub:
`@supabase/supabase-js` is not installed, so `useLive` holds its initial value
and reports `offline`. Per the walking-skeleton rule, polling is the dumb body
that makes the demo work now without changing that signature later.

## 4. Unfinished backend

### 4.1 The group lifecycle is implemented but never runs

`app/lifecycle.py` has `expire_invitations()`, `advance_group_for_time()` and
`transition_group()`, all pure, all tested. **Nothing calls any of them.** No
route, no scheduler, no CLI entry point:

```
$ grep -rn 'expire_invitations\|advance_group_for_time' app/ match.py
  (only app/lifecycle.py itself)
```

`GroupRepository.set_status()` has zero callers too, including in tests.
Confirmation happens through the atomic RPC instead, which is why it is unused.

At runtime, therefore: invitations never expire, and a group never leaves
`forming` or `confirmed` for `active`, `completed` or `dissolved`. The states
exist in the schema and in `GroupOut.state`, and two of the five are currently
unreachable. Anything the frontend builds on "the gap has started" has nothing
to read yet.

### 4.2 Favourite spots cannot be stored

`StudentRepository.list_spot_ids()` and `set_spots()` both read and write a
`student_spots` table. That table is **not in `sql/schema.sql`**. Both methods
catch Postgres error `PGRST205` (table not found) and return quietly, so
nothing 502s and nothing persists.

This is a consequence of this branch's own merge. `student_spots` was created
by `sql/002_plan_alignment.sql`, which was deleted during the lifecycle merge
because the rest of it rewrote columns the canonical schema no longer has. The
table went with it. The canonical schema never had it.

The visible effect is mild and misleading: `GET /me` echoes
`favourite_spots` back from the in-process `app/store.py`, so the value
survives until the backend restarts, is never read by the matcher, and is
invisible to any other process.

Knock-on effect on the meeting spot: `engine.pick_spot()` is documented as
"favourite spots, then shortest total walk". With `student_spots` absent, the
favourites half always receives empty lists, so building choice falls entirely
to the `spread` tie-break, which varies by group index to keep the map from
collapsing onto one pin.

### 4.3 Matching ignores every signal

`engine.form_groups()` groups on time overlap alone, by its own docstring.
AGENTS.md Tier 1 item 2 asks for "newcomer priority (low hangout counts
matched first)", and the Backend conventions section names
`shared_with(a, b)`. Neither exists; `grep -rn 'def shared_with' app/` finds
nothing. Groups are correct in size and timing and arbitrary in composition.

### 4.4 `walk_min` is a constant

`PLACEHOLDER_WALK_MIN = 5` in `app/groups_view.py`, returned for every spot.
Clearly labelled, honest, and it means "5 min walk for you" on the group card
is decoration. No distance data exists to replace it.

## 5. Concerns

### 5.1 `GET /groups/open` reveals the exact building to non-members

`OpenGroupOut.area` is `groups.building_name(...)`, the real building name, and
the endpoint is callable by any onboarded student.

The two AGENTS.md rules pull in opposite directions:

- "Before joining it shows only the time, the general area and what they
  share." A building name is more precise than a general area.
- "Meeting spots are public campus buildings, revealed only once the group is
  confirmed." These groups *are* confirmed, which permits it.

So it is defensible and it is also inconsistent with the group card, which
since this branch's lifecycle merge withholds `spot` until the caller has
joined. The same student learns the building from the open list and not from
the card. **Your call**, and it is a one-line change either way: keep it as
the thing that makes an open group joinable, or coarsen it to an area label.
I have changed nothing.

### 5.2 Fixture mode teaches a privacy rule the backend enforces

`fixtures.js` `meNow` returns `my_state: 'invited'` together with
`spot: { building: 'The Nest' }`. The real backend will not return that
combination any more: `spot_is_visible_to()` requires the caller to have
joined. Anyone developing screens with `VITE_USE_FIXTURES=true` sees the spot
before joining and would reasonably build as if that were allowed.

### 5.3 No privacy or group rule is broken by the code as it stands

Checked against the rules in AGENTS.md, in the serialisers rather than from
the route names: open groups, `/map` and `/projector` carry no names; map
counts below `MIN_GROUP_SIZE` are dropped rather than rounded; group first
names reach only joined callers and name only joined members; `/map` takes no
coordinate parameter; non-members get 404 from group detail. `MIN_GROUP_SIZE`
is one constant, set to 3.

## 6. Proposed order

Broken calls first, then new work in tier order. Nothing in step 1, so:

| # | Item | Tier | Touches | Blocked? |
| --- | --- | --- | --- | --- |
| 1 | Show `mode` on the group card and in the open list, and take the card's label from `group.mode` instead of the local toggle | 1 | `GroupCard.jsx`, `OpenGroupList.jsx`, `RightNow.jsx` | no |
| 2 | Poll `GET /projector` and `GET /map` so the demo's counts move | 1 | `useAsync.js` or a small `usePoll`, `Projector.jsx`, `MapPage.jsx` | no |
| 3 | Reset button on the Projector screen, demo mode only, wired to `GET /auth/config` | 1 | `api.js`, `authContext.js`, `Projector.jsx` | no |
| 4 | Send `courses` from onboarding, so `shared` carries course codes | 1 | `api.js`, `Onboarding.jsx` | needs `CURRENT_TERM` set on the backend |
| 5 | Edit name and tags from the Me screen | 2 | `Me.jsx` | no |
| 6 | Favourite spots editor | 2 | `Me.jsx` | **yes**, see 4.2 |

Items 1 to 3 are frontend-only and need no backend change. Item 4 needs an
environment variable, not a code change. Item 6 should not be built until
`student_spots` exists.

## For the backend owner

Ordered by what it costs the demo. I have changed none of this.

1. **Nothing calls the lifecycle functions** (4.1). `expire_invitations()` and
   `advance_group_for_time()` are written and tested but unreachable, so
   invitations never expire and no group ever becomes `active` or `completed`.
   A route or a periodic task would make three of the five group states real.
   `GroupRepository.set_status()` is dead code and can go.
2. **`student_spots` is missing from `sql/schema.sql`** (4.2). Favourite spots
   are accepted by two endpoints and silently discarded, and
   `engine.pick_spot()`'s favourites half never receives data. The table
   definition is recoverable from `sql/002_plan_alignment.sql` in this
   branch's history, at commit `97e4679^`.
3. **`CURRENT_TERM` has no default** (3.2). With it unset, any `POST /students`
   carrying courses is a 422. Either default it or let courses through without
   a term.
4. **Matching ignores all signals** (4.3). Tier 1 asks for newcomer priority
   and `shared_with(a, b)`; groups are currently time-overlap only.
5. **`StudentOut` omits `languages` and `ask_me_about`** (3.3) although
   `PATCH /me` accepts both. Write-only fields cannot be shown in an editor.
6. **`PLACEHOLDER_WALK_MIN`** (4.4) makes every walk five minutes. Fine as a
   placeholder; the group card is currently stating it as fact.
7. **Decide on `OpenGroupOut.area`** (5.1), which is the exact building name
   rather than a general area.

## Status

Phase 1 complete. Nothing has been changed outside this file. Waiting for
approval of all or part of section 6 before touching any code.
