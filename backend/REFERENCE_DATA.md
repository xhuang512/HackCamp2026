# Onboarding reference data

Student-type tags and languages are controlled catalogs. Courses remain flexible
but are stored under normalized, unique codes.

## Seed the catalogs

Apply `sql/001_core_schema.sql` and configure the root `.env` with
`SUPABASE_URL` and `SUPABASE_SERVICE_KEY`. Then run from `backend/`:

```bash
.venv/bin/python seed.py
```

The script upserts languages by `languages.code` and tags by `tags.slug`, so it
is safe to run repeatedly. Existing matching labels are updated to the seeded
canonical labels without creating duplicate rows.

## Read frontend options

Start FastAPI and request:

```bash
curl http://localhost:8000/options
```

The response uses canonical identifiers accepted by `POST /students`:

```json
{
  "languages": [{"id": "en", "label": "English"}],
  "tags": [{"id": "transfer", "label": "Transfer student"}]
}
```

Language inputs may use either the canonical code or an existing language name,
case-insensitively. Tag inputs use canonical slugs. Unknown controlled values
return HTTP 422.

Course inputs are uppercased and normalized to `SUBJ 123` or `SUBJ 123A` form.
For example, `stat406` becomes `STAT 406`. Existing course rows are reused and
valid missing courses are created with an upsert on the unique `courses.code`
column. Malformed course codes return HTTP 422.

## Test

Run all backend tests:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Run only the reference-data tests:

```bash
.venv/bin/python -m unittest tests.test_reference_data -v
```
