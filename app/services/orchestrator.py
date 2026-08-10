from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agents.crew import resume_crewai_incident, run_crewai_incident
from app.agents.deterministic import (
    resume_deterministic_incident,
    run_deterministic_incident,
)
from app.config import get_settings
from app.models.enums import IncidentStatus
from app.services.incident_service import IncidentService
from app.services.remediation import execute_approved_plan, reject_plan
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


def approve_and_resume(
    db: Session,
    incident_id: str,
    *,
    approved_by: str,
) -> dict[str, Any]:
    service = IncidentService(db)
    incident = service.get(incident_id)
    if not incident:
        raise ValueError("Incident not found")
    if incident.status != IncidentStatus.AWAITING_APPROVAL.value:
        raise ValueError(
            f"Incident is not awaiting approval (status={incident.status})"
        )

    service.approve_latest_plan(incident_id, approved_by)

    mode = (incident.agent_mode or resolve_agent_mode()).lower()
    if mode == "crewai":
        result = resume_crewai_incident(db, incident_id)
    else:
        result = resume_deterministic_incident(db, incident_id)

    # Fallback if resume helpers change
    if not result:
        result = execute_approved_plan(db, incident_id, already_approved=True)

    return {
        "result": result,
        "incident": service.get(incident_id),
    }


def reject_and_escalate(
    db: Session,
    incident_id: str,
    *,
    rejected_by: str,
    reason: str,
) -> dict[str, Any]:
    result = reject_plan(
        db, incident_id, rejected_by=rejected_by, reason=reason
    )
    return {
        "result": result,
        "incident": IncidentService(db).get(incident_id),
    }
