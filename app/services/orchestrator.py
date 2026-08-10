from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agents.crew import run_crewai_incident
from app.agents.deterministic import run_deterministic_incident
from app.config import get_settings
from app.services.incident_service import IncidentService
from app.tools.mock_state import mock_infra


def resolve_agent_mode() -> str:
    settings = get_settings()
    mode = (settings.aegis_agent_mode or "auto").lower()
    if mode == "auto":
        return "crewai" if settings.openai_api_key else "deterministic"
    if mode in {"crewai", "deterministic"}:
        if mode == "crewai" and not settings.openai_api_key:
            return "deterministic"
        return mode
    return "deterministic"


def simulate_incident(
    db: Session,
    *,
    scenario: str = "api_memory_pressure",
    service: str = "production-api",
    severity: str = "HIGH",
) -> dict[str, Any]:
    agent_mode = resolve_agent_mode()
    incident_service = IncidentService(db)
    incident = incident_service.create_incident(
        service=service,
        severity=severity,
        scenario=scenario,
        summary=f"Simulated incident ({scenario}) awaiting agent investigation",
        agent_mode=agent_mode,
    )
    mock_infra.bootstrap(incident.id, scenario=scenario)

    if agent_mode == "crewai":
        result = run_crewai_incident(db, incident.id)
    else:
        result = run_deterministic_incident(db, incident.id)

    detail = incident_service.get(incident.id)
    return {
        "agent_mode": agent_mode,
        "result": result,
        "incident": detail,
    }