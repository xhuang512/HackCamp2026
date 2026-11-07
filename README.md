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

Fill in the following values when Supabase integration is ready:

```dotenv
SUPABASE_URL=your-supabase-project-url
SUPABASE_KEY=your-supabase-key
```

The current health-check endpoint does not require Supabase credentials.

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

Supabase will be used for persistent data storage.

Database tables and connection setup are not yet finalized. Instructions will be added once the schema is ready.

## Development Notes

- Keep frontend and backend development servers running in separate terminals.
- Install Python dependencies from `backend/requirements.txt`.
- Install frontend dependencies using `npm ci`.
- Keep `.env` files, `.venv/`, and `node_modules/` out of Git.
- Commit `requirements.txt`, `package.json`, and `package-lock.json` to ensure teammates can install the required dependencies.
- The current repository provides the basic project structure. Authentication, matching logic, database integration, and application pages will be implemented separately.


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

