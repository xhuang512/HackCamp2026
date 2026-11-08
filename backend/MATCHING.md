# Development matching

The initial matcher forms deterministic groups of 3–5 students whose weekly
`free_blocks` share a common interval. It does not score courses, tags,
languages, newcomer priority, or walking distance yet.

## Prerequisites

Apply `sql/schema.sql` to a fresh project, then configure the root `.env` with
backend-only values:

```dotenv
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
GUEST_SESSION_SECRET=
CURRENT_TERM=
DEMO_MODE=true
```

The database needs at least one `buildings` row and at least three unpaused
students with overlapping free blocks. The matcher refuses to persist a group
when no building exists.

## Automatic matching

After `POST /students` saves the student's weekly free blocks, it runs the same
matching service for the next calendar occurrence of each available weekday.
That signup acts as a trigger for the whole waiting pool, so the first two
compatible students can receive a suggestion when a third student registers;
they do not need to register again.

Proposed and active groups with fewer than five members are considered first.
A waiting student is added only when one of their free blocks fully covers the
group time. Groups containing a skipped membership are not refilled because the
current schema has no explicit invitation lifecycle for safely replacing a
declined member.

Automatic matching is best-effort after onboarding has committed. A database
failure is logged without invalidating the new student's session; the next
signup or the batch CLI retries the waiting pool.

## Run matching

Run from `backend/`. Previewing is the default and does not write:

```bash
.venv/bin/python match.py --date 2026-11-10
```

Persist the previewed date only when demo mode is explicitly enabled:

```bash
.venv/bin/python match.py --date 2026-11-10 --apply
```

Proposed or active group members already assigned on that date are excluded, so
serial reruns do not duplicate their groups. This is deliberately stricter than
"same gap" and currently permits only one proposed/active assignment per student
per calendar date. The current schema has no database uniqueness key for a match
run or database-enforced group capacity, so concurrent signup requests or
multiple `--apply` commands for the same date can race.

## Exercise the API

`POST /students` returns a signed `session_token`. Pass it as a bearer token:

```bash
curl -H "Authorization: Bearer $SESSION_TOKEN" http://localhost:8000/me/now
curl -X POST -H "Authorization: Bearer $SESSION_TOKEN" \
  http://localhost:8000/groups/$GROUP_ID/join
curl -X POST -H "Authorization: Bearer $SESSION_TOKEN" \
  http://localhost:8000/groups/$GROUP_ID/skip
```

Before the student joins, `/me/now` hides names. The real building is returned
only after every membership has joined; until then the existing `spot` shape
contains `"building": "To be announced"`.

Run mocked tests with:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

The opt-in Supabase integration tests use `SUPABASE_URL` and
`SUPABASE_SERVICE_KEY`, create uniquely identified records, and require the
safe-write confirmation documented in the root README:

```bash
RUN_SUPABASE_INTEGRATION=1 .venv/bin/python -m unittest \
  tests.test_supabase_integration -v
```
