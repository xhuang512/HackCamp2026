# Integration report, 2026-11-08 (schedule pass)

Second pass. The first one covered the group lifecycle backend and is summarised
at the bottom under "Previous pass". This pass covers everything the backend
gained since the `last-integration` tag, which is one commit, `90b7438`,
"Add schedule AI integration and related tests".

Discovered from the code and from the running server's `/openapi.json`, not from
the commit message.

## Phase 1, discover

### What landed

`git diff last-integration -- backend/` is ten files, 1379 lines added, 2
changed. Six are new modules and tests; the two changed lines were import
conflicts, resolved in `7d77417`.

| File | What it is |
| --- | --- |
| `app/schedule.py` | Pure domain. `BusyInterval`, `merge_busy_intervals`, `suggest_free_blocks`, and the strict Pydantic shapes the AI is asked to return. No I/O, no FastAPI. |
| `app/schedule_ai.py` | The provider-agnostic seam: a `ScheduleParser` protocol, the extraction prompt, the error types, and `validate_schedule_image`. |
| `app/gemini_schedule.py` | The one Gemini implementation of that protocol. |
| `app/routers/schedule.py` | Two endpoints, below. |
| `app/repositories/free_blocks.py` | Gained `replace_for_student`, a delete-then-insert with a compensating rollback. |
| `tests/test_schedule.py` | 18 tests, 3 subtests. All pass. |

The seam between `schedule_ai.py` and `gemini_schedule.py` is worth noticing: no
route imports Gemini. Swapping providers is one factory function. This is the
walking-skeleton rule applied properly, and nothing below asks for it to change.

### Two new endpoints

| Endpoint | Request | Response | Does |
| --- | --- | --- | --- |
| `POST /schedule/parse` | `multipart/form-data`, field `image`. PNG, JPEG or WebP, max 10 MB, max 12000px per side, max 50M pixels. | `{timed_events, all_day_events, warnings, suggested_free_blocks, matching_window, availability_status}` | Sends the screenshot to Gemini, validates the structured reply against `ExtractedSchedule`, subtracts the visible events from the matching window, and returns suggestions. **Persists nothing** and triggers no matching. |
| `PUT /me/schedule` | `{free_blocks: [{day, start_time, end_time}]}`, at most 35, non-overlapping, `day` 0 to 6 with Monday 0 | `{status: "saved", free_blocks}` | Replaces the caller's Supabase `free_blocks` wholesale, then runs matching for each affected upcoming date, best-effort. |

`availability_status` is a constant, `"suggested_not_confirmed"`. It is the
backend saying in the payload that a parse result is not availability. Nothing
is saved until the student confirms.

Status codes I confirmed rather than inferred:

| Code | When |
| --- | --- |
| 401 | No token. Verified against the running server; the parser is never called. |
| 403 | Token fine, no profile. Both routes go through `onboarded_user`. See the onboarding gap below. |
| 413 | Image over 10 MB |
| 422 | Not an image, a content type that disagrees with the bytes, dimensions out of range, or overlapping blocks on the `PUT` |
| 429 | Gemini rate limited |
| 502 | Gemini failed or returned something that would not validate; or the free-block replacement failed and was rolled back |
| **503** | `GOOGLE_CLOUD_GEMINI_API_KEY` unset. Detail: `"Schedule parsing is not configured"`. |

That 503 is the state the repo is in right now: there is no key in any `.env`,
so every `POST /schedule/parse` returns it. I confirmed the exact code and
detail string by calling the dependency directly, because last pass I reported a
status code from reading the source and got it wrong.

### Frontend inventory

`src/lib/api.js` exports 18 backend functions. Every endpoint the server serves
has one except the two new ones.

| Screen | Calls |
| --- | --- |
| `Welcome.jsx` | `getAuthConfig` |
| `Onboarding.jsx` | `getOptions`, `createStudent` |
| `RightNow.jsx` | `getMeNow`, `getOpenGroups`, `getOptions`, `createGroup`, `joinGroup`, `skipGroup` |
| `MapPage.jsx` | `getMap` |
| `Projector.jsx` | `getProjector`, `getAuthConfig`, `adminReset` |
| `Me.jsx` | `getMe`, `getOptions`, `patchMe`, `setPaused` |
| `CheckInCode.jsx` | `getCheckinCode` |
| `CheckInScanner.jsx` | `postCheckin` |

`getGroup` and `getHealth` exist in `api.js` with no caller. Neither is broken.

### Broken calls

**None.** No endpoint was removed and no response shape changed. The only
contract-level edit in `90b7438` was additive.

Two things that are not broken but would have broken on the first attempt:

1. `request()` in `api.js` sets `Content-Type: application/json` and
   `JSON.stringify`s every body. A multipart upload cannot go through it.
   `POST /schedule/parse` needs its own path that passes a `FormData` straight
   to `fetch` and lets the browser set the boundary.
2. `PUT` is not among the methods `request()` is used with today. It takes
   `method` as a parameter, so this is nothing, but worth saying it was checked.

### New or unused endpoints

| Endpoint | Belongs in | Tier |
| --- | --- | --- |
| `POST /schedule/parse` | A schedule section on `Me.jsx`: upload, then a review list | **Tier 2**, "Gemini schedule parsing with a review screen". Also named under `Later:` in the AGENTS.md contract table. |
| `PUT /me/schedule` | The Save button on that review list | **Not in AGENTS.md.** It is the persistence half of the same Tier 2 item, so it inherits the tier, but the contract table does not mention it and should. |

### Unfinished backend

- **Parsing is unconfigured, so the feature is a 503 today.** Not a defect. It
  needs `GOOGLE_CLOUD_GEMINI_API_KEY` in the root `.env`. Anything the frontend
  ships has to treat 503 as a first-class state, not an error banner, because
  503 is what the demo will show unless someone adds a key.
- **`GEMINI_MODEL` defaults to `gemini-3.8-flash`.** I cannot verify that model
  name resolves without a key. If it does not, every call is a 502.
- **`genai.Client(enterprise=True, ...)`** is an unusual argument. Unverifiable
  here for the same reason. Both of these are first-call-with-a-real-key risks,
  not code to change.
- **`/auth/config` says nothing about schedule parsing.** It already reports
  `demo_mode` and whether Auth0 and the guest secret are set, and `Welcome.jsx`
  uses it for exactly this kind of pre-flight. There is no equivalent question
  for parsing, so the frontend cannot know before the student picks a file. See
  "For the backend owner".
- `tests/test_gemini_schedule_integration.py` is skipped unless
  `RUN_GEMINI_INTEGRATION=1`. Correct, and it is one of the 7 skips.

### Concerns

**1. The confirmed schedule lands in one store and the gap label reads the
other.** This is the one that blocks the feature, so it is first.

Identity is still split (`docs/HANDOFF.md` section 3): `app/store.py` holds the
authenticated profile, Supabase holds the matchable row. `POST /students` writes
both. `PUT /me/schedule` writes **only** the Supabase `free_blocks` table.

`GET /me/now` reads both, from different places:

- the suggested group comes from `FreeBlockRepository.list_for_student`, which
  is Supabase, so it **does** see the confirmed schedule
- `_next_gap(student)` in `routers/students.py:115` reads
  `store.Student.free_blocks`, which **does not**

So a student who uploads a screenshot and confirms it gets groups matched
against their real availability, under a header still showing the gap from the
preset they picked during onboarding. The header is the first line on the app's
main screen. Shipping a review screen on top of this means shipping a screen
whose effect is invisible and, where it is visible, wrong.

Also downstream of the same gap: `_aha_for` in `routers/identity.py:300` and
`store.overlap_count`, both store-only.

This is the "bug that blocks the frontend" case, so a minimal backend fix is in
scope: have `PUT /me/schedule` write the store half too, the way
`POST /students` already does. Nothing else about the endpoint changes.

**2. The screenshot goes to a third party.** AGENTS.md: "Timetables, classrooms
and points balances stay private to their owner." A timetable screenshot sent to
Google is a disclosure that rule does not contemplate, and a screenshot carries
more than a timetable: section numbers, room numbers, sometimes a student number
in a header.

The backend handles its side carefully. `parse_schedule` resolves auth before
reading a byte, then `del student_id`, with a comment saying the opaque id is
not sent to the provider or logged. Nothing is persisted. The prompt tells the
model not to infer availability.

What is missing is on my side: the student is never told. A file picker that
silently uploads their timetable to Google is not consent. The upload entry
point needs to say where the image goes, before the picker opens, and it needs
to be skippable, which it is, because presets still exist.

I am treating this as a copy and consent requirement on the frontend, not a
reason to stop. Flagging it rather than deciding it: **if the team would rather
not send timetables off-box at all, say so and this feature does not ship.**

**3. All-day events are extracted and then ignored.**
`busy_intervals_from_extraction` iterates `extraction.timed_events` only.
`all_day_events` is parsed, returned, and never subtracted. An all-day
"Conference" or "Reading break" produces a suggestion that the student is free
09:00 to 18:00 that day.

Not a privacy breach, and the review screen is the mitigation: the student sees
every suggested block before anything saves, and can delete one. But the
suggestion is wrong by default on exactly the days it matters, and the fix is
one loop. In "For the backend owner" rather than changed here, because changing
which events count as busy is a behaviour decision, not a blocking bug. The
review screen must show `all_day_events` so the student can see the thing the
suggestion ignored.

**4. Neither schedule endpoint can be reached during onboarding.** Both depend
on `get_current_student_id`, which goes through `onboarded_user`, which 403s
without a profile. There is no profile until `POST /students` at the end of
onboarding.

So the screenshot flow cannot be an onboarding step. Onboarding step 2 currently
says "Uploading a screenshot of your timetable comes later", which happens to be
accurate, but it reads like a promise about a later release rather than a
description of where the feature lives.

I am not changing the auth on those routes: a profile-less caller is a
deliberate 403 and loosening it to `current_user` would need `POST /students` to
accept a parse result, which is a contract change. The feature goes on `Me.jsx`,
where it works. Noted for the backend owner.

**5. No way to read the confirmed schedule back.** `GET /me` returns
`StudentOut`, which is `{id, first_name, is_guest, paused, visibility, tags,
favourite_spots}`. No `free_blocks`. `PUT /me/schedule` replaces wholesale.

So the frontend can write a schedule and never show it. The parse-review-save
flow does not need a read, because the suggestions come from the parse response,
which is why this is not a blocker. But a student cannot see or edit what they
saved, and "replace wholesale" plus "cannot read" means the only way to adjust
one block is to re-upload the screenshot. For the backend owner.

### Proposed order

Broken calls: none, so nothing in Phase 2.

1. **The store/Supabase split on `PUT /me/schedule`** (concern 1). Minimal
   backend fix. Everything else is pointless without it.
2. **`api.js`: `parseSchedule` and `putSchedule`.** One function per endpoint,
   plus the multipart path `request()` cannot take.
3. **The review screen on `Me.jsx`.** Upload, consent copy before the picker,
   then the parsed events and the suggested blocks with per-block removal, then
   Save. Loading, empty, error and the 503 "not configured" state.
4. **AGENTS.md contract table**, which does not list either endpoint.

Not proposed, deliberately: an onboarding screenshot step (concern 4, blocked by
auth), a schedule viewer on `Me.jsx` (concern 5, no read endpoint),
all-day-event handling (concern 3, backend behaviour).

---

*Phases 2 to 4 of this pass are appended below once approved.*

---

# Previous pass, 2026-11-08 (group lifecycle)

The first integration pass, against the group lifecycle backend, is recorded in
the commit history from `97e4679` to `9badc57`. Its findings that remain open:

### For the backend owner

Still open from the lifecycle pass, none acted on in this pass:

1. **`lifecycle.py` has no callers.** `expire_invitations()` and
   `advance_group_for_time()` are written, tested and never invoked, so
   invitations never expire and no group reaches `active`. AGENTS.md makes
   10-minute expiry a group rule and `active` a group state. This is the largest
   gap between the spec and the running server.
2. **`student_spots` is missing from `schema.sql`**, so `PATCH /me` accepts
   `favourite_spots` and silently discards it, which blocks a favourite-spots
   editor.
3. **`CURRENT_TERM` has no default**, and `POST /students` is a 503 without it.
4. **Matching ignores every signal**: no newcomer priority, no shared tags, no
   shared courses. AGENTS.md asks for newcomer priority in Tier 1.
5. **`StudentOut` omits `languages` and `ask_me_about`**, both of which
   onboarding collects.
6. **`PLACEHOLDER_WALK_MIN`** is a constant where a walking time should be.
7. **`OpenGroupOut.area`** wording decision, still open.
8. **`/auth/config` reports `guest_token_secret_set: false`** when the secret is
   set under the compatibility name `GUEST_SESSION_SECRET`.

### New, from this pass

9. **`PUT /me/schedule` cannot be reached during onboarding** (concern 4). Both
   schedule routes 403 without a profile, so the screenshot flow cannot be an
   onboarding step. Reaching it would mean either relaxing those routes to
   `current_user` and keying the write on something other than a student id, or
   letting `POST /students` accept a parse result.
10. **All-day events never count as busy** (concern 3).
    `busy_intervals_from_extraction` reads `timed_events` only, so an all-day
    event yields a full free day. One loop in `app/schedule.py`.
11. **No read endpoint for confirmed free blocks** (concern 5). `StudentOut`
    has no `free_blocks` and `PUT /me/schedule` replaces wholesale, so a saved
    schedule can never be shown or adjusted block by block.
12. **`/auth/config` cannot say whether parsing is configured.** It already
    answers the same question for Auth0, the guest secret and demo mode. A
    `schedule_parsing_configured` boolean would let the upload entry point
    explain itself before the student picks a file, instead of after.
13. **`GEMINI_MODEL` defaults to `gemini-3.8-flash`** and
    `genai.Client(enterprise=True, …)` are both unverifiable without a key.
    Worth one real call before the demo.
