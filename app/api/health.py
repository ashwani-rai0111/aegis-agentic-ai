from fastapi import APIRouter

from app.database.session import check_db
from app.models.schemas import HealthResponse
from app.services.orchestrator import resolve_agent_mode, resolve_tool_backend
from app.tools.backend import aws_settings_ready

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    db_ok = check_db()
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        database="up" if db_ok else "down",
        agent_mode=resolve_agent_mode(),
        tool_backend=resolve_tool_backend(),
        aws_configured=aws_settings_ready(),
    )
