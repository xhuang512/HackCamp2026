# Development matching

The initial matcher forms deterministic groups of 3–5 students whose weekly
`free_blocks` share a common interval. It does not score courses, tags,
languages, newcomer priority, or walking distance yet.

## Prerequisites

Apply `sql/001_core_schema.sql`, then configure the root `.env` with backend-only
values:

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
serial reruns do not duplicate their groups. The current schema has no database
uniqueness key for a match run, so do not run multiple `--apply` commands for the
same date concurrently.

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
only after every non-skipped member has joined; until then the existing `spot`
shape contains `"building": "To be announced"`.

Run mocked tests with:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

The opt-in Supabase integration test creates and removes a temporary student:

```bash
RUN_SUPABASE_INTEGRATION=1 .venv/bin/python -m unittest \
  tests.test_supabase_integration -v
```
