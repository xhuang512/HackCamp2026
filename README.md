# HackCamp 2026 — Hangout

A web application built for HackCamp 2026, using a React/Vite frontend, FastAPI backend, and Supabase database.

## Tech Stack

- **Frontend:** React + Vite
- **Backend:** Python + FastAPI
- **Database:** Supabase (PostgreSQL)
- **PWA:** vite-plugin-pwa (configuration pending)

## Prerequisites

Make sure the following are installed:

- [Node.js](https://nodejs.org/) 20.19+ or 22.12+
- [Python](https://www.python.org/downloads/) 3.11+
- Git
- npm (included with Node.js)

## Project Structure

```text
HackCamp2026/
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI application and routes
│   │   ├── auth.py        # Authentication (planned)
│   │   ├── engine.py      # Matching logic (planned)
│   │   └── codes.py       # Group codes (planned)
│   ├── seed.py            # Database seeding (planned)
│   └── requirements.txt   # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── pages/         # Application pages
│   │   ├── components/    # Reusable UI components
│   │   ├── lib/           # API and realtime utilities
│   │   └── styles/        # Shared styling
│   ├── public/            # Static assets
│   └── package.json      # Frontend dependencies
├── sim/                   # Simulation utilities
├── .env.example           # Environment variable template
├── .gitignore
└── README.md
```

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/xhuang512/HackCamp2026.git
cd HackCamp2026
```

### 2. Set Up the Backend

From the project root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cd ..
```

On Windows PowerShell, activate the virtual environment with:

```powershell
.venv\Scripts\Activate.ps1
```

### 3. Configure Environment Variables

From the project root:

```bash
cp .env.example .env
```

Fill in the backend values and list every frontend origin that may call FastAPI:

```dotenv
SUPABASE_URL=your-supabase-project-url
SUPABASE_SERVICE_KEY=your-backend-only-service-role-key
GUEST_SESSION_SECRET=at-least-32-bytes
CURRENT_TERM=2026W1
DEMO_MODE=false
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
GOOGLE_CLOUD_GEMINI_API_KEY=your-google-cloud-gemini-api-key
GEMINI_MODEL=gemini-3.8-flash
SCHEDULE_MATCHING_DAYS=0,1,2,3,4
SCHEDULE_MATCHING_WINDOW_START=09:00
SCHEDULE_MATCHING_WINDOW_END=18:00
```

`CORS_ORIGINS` is a comma-separated list of exact origins. For LAN phone testing,
add the frontend development server's LAN origin, such as
`http://192.168.1.20:5173`. For deployment, add the exact HTTPS frontend origin.
Do not use `*`; the API accepts bearer credentials and deliberately rejects an
unrestricted wildcard origin.

The health-check endpoint does not require Supabase credentials. Other data
endpoints require `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`.

The frontend's `VITE_API_URL` is public configuration and should be set in
`frontend/.env.local` for local development or in the frontend hosting provider.
Never expose `SUPABASE_SERVICE_KEY` through a `VITE_*` variable.

**Important:** Do not commit `.env` or any secrets to GitHub.

### 4. Set Up the Frontend

From the project root:

```bash
cd frontend
npm ci
cd ..
```

## Running Locally

Run the frontend and backend in separate terminals.

### Backend

From the project root:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Health check: http://localhost:8000/health
- Interactive API documentation: http://localhost:8000/docs

### Frontend

Open a second terminal from the project root:

```bash
cd frontend
npm run dev
```

Open http://localhost:5173 in your browser.

## Useful Commands

Run the following from the `frontend/` directory:

```bash
npm run lint      # Check code with ESLint
npm run build     # Create a production build
npm run preview   # Preview the production build
```

## Database Setup

Apply `backend/sql/schema.sql` once to a completely fresh Supabase project, then
seed the controlled onboarding catalogs:

```bash
cd backend
.venv/bin/python seed.py
```

The backend uses the service-role key for privileged database access. Browser
clients call FastAPI and do not receive that key.

### Lifecycle V2 schema

Lifecycle V2 is the only schema supported by the backend. The canonical schema
creates the final `groups` and `group_members` tables directly, enables RLS,
installs the atomic `respond_to_group_invitation` RPC, and grants that RPC only
to the service role. It also uses current Vancouver timezone rules for meeting
deadlines; install the backend's pinned dependencies so Python uses matching
IANA timezone data.

`schema.sql` is a fresh-install schema, not an upgrade script. Do not apply it
over an existing database. A database that was already initialized with the
former migration sequence should be inspected separately before any schema
changes. Schema installation is never performed automatically at application
startup.

### Live Supabase integration validation

The main integration tests use the backend's normal Supabase configuration.
Point these variables at a database that is safe for temporary test writes. The
database does not need to be empty: test students, groups, memberships, and the
test building receive a unique prefix or identifier, and cleanup targets only
those records.

```bash
export SUPABASE_URL=<test-or-staging-project-url>
export SUPABASE_SERVICE_KEY=<test-or-staging-service-role-key>
export SUPABASE_TEST_CONFIRM_WRITES=YES_I_AM_USING_A_SAFE_TEST_DATABASE
```

Run the real Supabase lifecycle tests explicitly:

```bash
cd backend
RUN_SUPABASE_INTEGRATION=1 .venv/bin/python -m pytest \
  tests/test_lifecycle_supabase_integration.py -v
```

The tests remain skipped unless `RUN_SUPABASE_INTEGRATION=1` is set and refuse
to write without the exact confirmation above. Automatic matching is suppressed
during live registration so a shared staging database cannot pull unrelated
students into test groups; deterministic repository tests cover that trigger.
The live suite creates its own memberships and exercises lifecycle confirmation,
privacy, idempotency, invalid and expired responses, and concurrent acceptances.

Anonymous RLS tests are a separate optional class. Add the normal public key to
run them; the main API integration tests do not require it:

```bash
export SUPABASE_ANON_KEY=<test-or-staging-anon-key>
```

### Optional SQL setup for a fresh project

Schema installation is separate from API integration testing. Only when
initializing a confirmed empty disposable project, export the direct connection
and project-reference safeguards, then run the setup script:

```bash
export SUPABASE_DB_URL=<empty-disposable-postgres-connection-string>
export SUPABASE_PROJECT_REF=<disposable-project-ref>
export SUPABASE_SQL_SETUP_CONFIRM_PROJECT_REF=<disposable-project-ref>
export SUPABASE_SQL_SETUP_CONFIRM_EMPTY=YES_INITIALIZE_EMPTY_DATABASE
backend/scripts/setup_lifecycle_test_db.sh
```

The setup script refuses a database that already contains `public.students`,
requires the project reference to appear in `SUPABASE_DB_URL`, and applies
`schema.sql` with PostgreSQL's stop-on-first-error behavior. None of these
SQL-setup variables are required by the backend or API integration tests.

## Frontend API integration contract

`POST /students` accepts a first name of at most 40 characters and returns a
signed guest `session_token`. Send that token to authenticated endpoints as:

```http
Authorization: Bearer <session_token>
```

`GET /me/now` has two successful HTTP 200 response variants.

When a suggestion exists, the established shape is unchanged. The `gap` fields
now contain the persisted group's actual meeting date and interval:

```json
{
  "gap": {"day": "tue", "start": "13:15", "end": "14:30"},
  "group": {
    "id": "group-id",
    "members": [],
    "shared": ["STAT 302"],
    "spot": {"building": "To be announced", "walk_min": 0},
    "response": "pending",
    "status": "forming",
    "accepted_count": 2,
    "minimum_required": 3,
    "invite_expires_at": "2026-11-10T13:05:00-08:00"
  }
}
```

When the authenticated student has no current suggestion, the response is:

```json
{"status": "waiting"}
```

The frontend should treat this as a normal waiting state, not an error. Missing
or invalid authentication remains HTTP 401. Database and Supabase failures remain
HTTP 502 or 503. Validation failures remain HTTP 422.

Names remain hidden until the requesting student joins, and only accepted
members' names are returned. The real meeting building is visible only to an
accepted member after the group reaches three acceptances and becomes confirmed
or active.

### Schedule screenshot import

`POST /schedule/parse` accepts an authenticated multipart PNG, JPEG, or WebP
calendar screenshot up to 10 MB. The backend validates the actual image bytes
and dimensions, sends the bytes directly to Google Cloud Gemini, and
returns strictly validated timed events, separate all-day events, warnings, and
suggested free blocks. Images and parsed timetables are not stored, and this
endpoint never triggers matching.

Configure the backend-only Google Cloud Gemini key and model:

```dotenv
GOOGLE_CLOUD_GEMINI_API_KEY=your-google-cloud-gemini-api-key
GEMINI_MODEL=gemini-3.8-flash
```

The Gemini adapter uses Google Cloud's Gemini Enterprise Agent Platform through
`aiplatform.googleapis.com/v1`, not the Google AI Studio
`generativelanguage.googleapis.com` endpoint. Configure the key through
`GOOGLE_CLOUD_GEMINI_API_KEY`. A standard Google Cloud key must be bound to a
service account whose project role includes `aiplatform.endpoints.predict`.
Google's quickstart recommends Agent Platform User (`roles/aiplatform.user`);
the standard-key setup guide uses Agent Platform Express User
(`roles/aiplatform.expressUser`) for the key's bound service account. A key
created directly through Agent Platform express mode does not require that
additional IAM grant.

`GEMINI_MODEL` defaults to `gemini-3.8-flash`. The Gemini key must never be
placed in `VITE_*` settings.

The default suggestion window is weekdays from
09:00 through 18:00 in `America/Vancouver`; override it with
`SCHEDULE_MATCHING_DAYS`, `SCHEDULE_MATCHING_WINDOW_START`, and
`SCHEDULE_MATCHING_WINDOW_END`. Day numbers use Monday=0 through Sunday=6.

The parse response marks every calculated block as
`"availability_status": "suggested_not_confirmed"`. A gap in visible calendar
events is not proof of personal availability, and a one-week screenshot is not
treated as a recurring schedule. The frontend must let the student review and
edit the suggestions before saving them.

With a guest session returned by `POST /students`:

```bash
curl -X POST http://localhost:8000/schedule/parse \
  -H "Authorization: Bearer $SESSION_TOKEN" \
  -F "image=@calendar.png;type=image/png"
```

Restart the FastAPI process after changing Gemini configuration so it reloads
the environment.

`PUT /me/schedule` persists only the authenticated student's reviewed blocks,
replacing their prior availability and then attempting the existing automatic
matching flow:

```bash
curl -X PUT http://localhost:8000/me/schedule \
  -H "Authorization: Bearer $SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"free_blocks":[{"day":1,"start_time":"13:00","end_time":"15:00"}]}'
```

Schedule replacement does not cancel, decline, or alter existing invitations,
and it never dissolves confirmed or active groups. The new blocks affect future
matching attempts only. Cancellation and invitation reconciliation remain a
separate lifecycle feature. Under the existing `/me/now` contract, a group whose
meeting interval is no longer covered by the student's reviewed free blocks may
stop being selected as the current suggestion even though its membership record
is preserved; the frontend should warn users before removing availability that
covers an outstanding invitation or accepted group.

Confirmed blocks are stored in the existing weekly `free_blocks` format. The
frontend should make that weekly meaning explicit at confirmation time; the
parser itself never infers recurrence from a one-week screenshot.

The persistence layer batches the new rows and attempts a compensating restore
if insertion fails after deleting the old blocks. Because those are separate
PostgREST requests, a process or network failure during the small gap cannot be
fully transactional; a future database RPC can close that residual failure
window without changing the API contract.

### Optional real Gemini validation

Mocked Gemini tests run in the ordinary suite. The live vision test is disabled
unless `RUN_GEMINI_INTEGRATION=1` and does not connect to Supabase. It uses the
reference screenshot at `~/Downloads/schedule_test.png`.

Then run:

```bash
cd backend
RUN_GEMINI_INTEGRATION=1 .venv/bin/python -m pytest \
  tests/test_gemini_schedule_integration.py -v
```

The test loads the root `.env`, calls Google Cloud Gemini only after the explicit flag, and
verifies the expected 13 timed events by weekday and start/end time. It performs
no database writes.

## Development Notes

- Keep frontend and backend development servers running in separate terminals.
- Install Python dependencies from `backend/requirements.txt`.
- Install frontend dependencies using `npm ci`.
- Keep `.env` files, `.venv/`, and `node_modules/` out of Git.
- Commit `requirements.txt`, `package.json`, and `package-lock.json` to ensure teammates can install the required dependencies.
- Authentication, matching, and Supabase persistence are implemented in the
  backend. The frontend application pages and API integration are still pending.


# UBC Study & Social Meetups

A mobile-first web app concept for UBC students to find study groups and social meetups that fit between classes. Students can discover a group during a shared timetable gap or scan a QR code at a campus building to start or join a meetup.

## Why we’re building it

A break between classes is an opportunity to meet classmates, but coordinating schedules and finding somewhere to meet can take longer than the break itself. We’re designing around three details students need to decide whether to join: what the group is doing, when it ends, and whether there’s room.

## How it works

- **Find a group during a class gap.** Students review their free blocks and choose Study or Social. Study suggestions prioritize shared courses. Social suggestions can use shared interests. Each suggestion shows the time and why it matches.
- **Scan a campus QR code.** A code opens the building’s Open Tables page. The app requires verified UBC student sign-in before students can view, host, or join sessions.
- **Start or join an Open Table.** A host chooses Study or Social, adds a topic or activity, sets the number of seats, and picks an end time. Students who opted in and have overlapping availability can receive an invite. The app shares the exact table location after joining and closes the listing at its end time.
- **Earn points for showing up.** Students confirm whether they met up afterward. The proposed rules award 10 points for attending a confirmed meetup or 20 total for hosting one an attendee confirms. A Community Host badge could recognize students who host three confirmed meetups.

| Meetup type | Example |
| --- | --- |
| Study | STAT 302 practice problems at Koerner Library, 1:15–2:00 PM, two seats open |
| Social | Coffee break at the Nest, 1:30–2:00 PM, three seats open |

## HackCamp demo

1. A host scans the Koerner Library QR code and opens a STAT 302 study table.
2. A classmate with a matching free block receives an invite, joins, and sees where to meet.
3. After the session, the classmate confirms the meetup and the host sees the points they earned.

The demo can use one building and sample timetables. The campus map and timetable screenshot import can follow once this flow works.

## Student access and privacy

- QR codes identify a building. Student verification controls access to its sessions.
- Matching uses shared free blocks while keeping full timetables private.
- Meetups take place in public venues. Exact table details are shared with members who join.

## Future direction

Extend Open Tables to public libraries, community centres, and other public venues in nearby municipalities. Commuter students could select areas that work for them and add evening or weekend availability. For example, a student who leaves campus after class could find a STAT 302 study group at a library in Richmond without sharing their home address.
