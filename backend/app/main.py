from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import admin, groups, projector, students

app = FastAPI(title="Hangout API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(students.router)
app.include_router(groups.router)
app.include_router(projector.router)
app.include_router(admin.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
