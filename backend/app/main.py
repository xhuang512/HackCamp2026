import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import admin, groups, options, projector, schedule, students

ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def parse_cors_origins(value: str) -> list[str]:
    origins = list(
        dict.fromkeys(
            origin.strip().rstrip("/")
            for origin in value.split(",")
            if origin.strip()
        )
    )
    if not origins:
        raise RuntimeError("CORS_ORIGINS must contain at least one frontend origin")
    for origin in origins:
        parsed = urlsplit(origin)
        if origin == "*":
            raise RuntimeError(
                "CORS_ORIGINS cannot contain '*' when credentials are enabled"
            )
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise RuntimeError(
                f"Invalid CORS origin '{origin}'; use an exact http(s) origin"
            )
    return origins


load_dotenv(ROOT_ENV_FILE, override=False)

app = FastAPI(title="Hangout API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_cors_origins(
        os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(students.router)
app.include_router(schedule.router)
app.include_router(options.router)
app.include_router(groups.router)
app.include_router(projector.router)
app.include_router(admin.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
