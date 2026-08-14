from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, fixes, health, incidents
from app.database.session import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Aegis — Autonomous AI Operations Agent",
    description=(
        "Agentic incident response using CrewAI (or deterministic fallback), "
        "mock or live AWS tools (CloudWatch/EC2/SSM), PostgreSQL audit storage, "
        "and Cursor Cloud code-fix jobs (separate Code Fixes surface)."
    ),
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(incidents.router)
app.include_router(fixes.router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "Aegis",
        "docs": "/docs",
        "health": "/health",
        "simulate": "POST /incidents/simulate",
        "live": "POST /incidents/live",
        "investigate": "POST /incidents/investigate",
        "fixes": "POST /fixes",
        "fix_repos": "GET /fixes/repos",
    }