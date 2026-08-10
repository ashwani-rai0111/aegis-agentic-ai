from fastapi import APIRouter

from app.config import get_settings
from app.database.session import check_db
from app.models.schemas import HealthResponse
from app.services.orchestrator import resolve_agent_mode

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    db_ok = check_db()
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        database="up" if db_ok else "down",
        agent_mode=resolve_agent_mode(),
    )