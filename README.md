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

Apply `backend/sql/001_core_schema.sql` to the Supabase project, then seed the
controlled onboarding catalogs:

```bash
cd backend
.venv/bin/python seed.py
```

The backend uses the service-role key for privileged database access. Browser
clients call FastAPI and do not receive that key.

### Group lifecycle migration rollout

Lifecycle V2 is the only schema supported by the backend. A fresh database must
apply `backend/sql/001_core_schema.sql` followed by
`backend/sql/002_group_lifecycle.sql` before the API starts accepting traffic.
The second migration renames `group_members.response` to `invitation_status`,
adds lifecycle timestamps and constraints, and installs the atomic
`respond_to_group_invitation` RPC.

For an existing V1 database, use a coordinated maintenance deployment:

1. Back up the database and pause all API and matching writes.
2. Verify that the live schema still has `groups_status_check`,
   `group_members_response_check`, and `group_members.response` from migration
   001. The migration is intended to run exactly once.
3. Apply `backend/sql/002_group_lifecycle.sql` in Supabase.
4. Deploy/restart this V2-only backend, then resume writes.

Do not deploy this backend against a V1 database: it always queries
`invitation_status` and calls `respond_to_group_invitation`. Likewise, do not
resume an older backend after applying migration 002. The migration is not
applied automatically by application startup and must first be exercised in a
disposable or staging Supabase project.

### Disposable lifecycle validation

Lifecycle integration tests intentionally do not use `SUPABASE_URL` or
`SUPABASE_SERVICE_KEY`. Create a new, empty Supabase project that can be deleted
after testing, then export separately named test credentials in the current
shell. Do not put these values in the repository or copy data from another
project.

```bash
export LIFECYCLE_TEST_PROJECT_REF=<disposable-project-ref>
export LIFECYCLE_TEST_DB_URL=<disposable-postgres-connection-string>
export LIFECYCLE_TEST_SUPABASE_URL=<disposable-project-url>
export LIFECYCLE_TEST_SERVICE_KEY=<disposable-service-role-key>
export LIFECYCLE_TEST_ANON_KEY=<disposable-anon-key>
export LIFECYCLE_TEST_CONFIRM_DISPOSABLE=YES_DELETE_TEST_DATA
```

Install the schema only after verifying that every value identifies the new
project:

```bash
backend/scripts/setup_lifecycle_test_db.sh
```

The setup script refuses databases that already contain `public.students`,
requires the project reference to appear in the connection string, and applies
`001_core_schema.sql` followed by `002_group_lifecycle.sql` with PostgreSQL's
stop-on-first-error behavior.

Run the real Supabase lifecycle tests explicitly:

```bash
cd backend
RUN_LIFECYCLE_V2_INTEGRATION=1 .venv/bin/python -m pytest \
  tests/test_lifecycle_supabase_integration.py -v
```

The test suite also refuses to run when the test URL equals the normal
development `SUPABASE_URL`, requires an empty students/groups dataset, uses a
unique test prefix, and removes only rows created through its dedicated test
building and prefix. It exercises automatic matching, lifecycle confirmation,
privacy, idempotency, invalid and expired responses, anonymous RLS/RPC denial,
and concurrent acceptances.

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
