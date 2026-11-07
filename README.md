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
