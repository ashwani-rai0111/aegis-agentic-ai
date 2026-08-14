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
from app.services.issue_scope import out_of_scope_reason
from app.services.remediation import execute_approved_plan, reject_plan
from app.tools.aws_clients import get_boto_session
from app.tools.backend import aws_settings_ready, resolve_tool_backend_name
from app.tools.mock_state import mock_infra

LIVE_SCENARIO = "live_aws"
USER_REPORT_SCENARIO = "user_report"


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


def resolve_tool_backend() -> str:
    return (get_settings().aegis_tool_backend or "mock").lower()


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


def _ensure_live_aws_ready() -> None:
    settings = get_settings()
    if (settings.aegis_tool_backend or "").lower() != "aws":
        raise ValueError(
            "Live/investigate requires AEGIS_TOOL_BACKEND=aws in .env "
            "(simulate still works with mock)."
        )
    if not aws_settings_ready():
        raise ValueError(
            "Missing AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, or AEGIS_EC2_INSTANCE_ID"
        )
    if not settings.aegis_cw_alarm_name:
        raise ValueError("AEGIS_CW_ALARM_NAME is required for live incidents")
    get_settings.cache_clear()
    get_boto_session.cache_clear()


def run_live_incident(
    db: Session,
    *,
    service: str = "production-api",
    severity: str = "HIGH",
    user_message: str | None = None,
) -> dict[str, Any]:
    """Create an incident against real AWS (no mock bootstrap)."""
    _ensure_live_aws_ready()
    settings = get_settings()

    agent_mode = resolve_agent_mode()
    incident_service = IncidentService(db)
    summary = (
        user_message.strip()
        if user_message and user_message.strip()
        else (
            f"Live AWS incident on {settings.aegis_ec2_instance_id} "
            f"(alarm={settings.aegis_cw_alarm_name})"
        )
    )
    incident = incident_service.create_incident(
        service=service,
        severity=severity,
        scenario=LIVE_SCENARIO if not user_message else USER_REPORT_SCENARIO,
        summary=summary,
        agent_mode=agent_mode,
    )
    if user_message and user_message.strip():
        incident_service.add_observation(
            incident.id,
            source="user",
            name="reported_issue",
            value=user_message.strip(),
            evidence={"message": user_message.strip()},
        )
    # Intentionally no mock_infra.bootstrap — tools resolve to AwsBackend.

    if agent_mode == "crewai":
        result = run_crewai_incident(
            db, incident.id, user_message=user_message
        )
    else:
        result = run_deterministic_incident(
            db, incident.id, user_message=user_message
        )

    detail = incident_service.get(incident.id)
    return {
        "agent_mode": agent_mode,
        "tool_backend": resolve_tool_backend_name(incident.id),
        "result": result,
        "incident": detail,
    }


def investigate_user_issue(
    db: Session,
    *,
    message: str,
    service: str = "signyn",
    severity: str = "HIGH",
) -> dict[str, Any]:
    """Dashboard free-text issue → live AWS investigation."""
    text = (message or "").strip()
    rejected = out_of_scope_reason(text)
    if rejected:
        raise ValueError(rejected)
    return run_live_incident(
        db,
        service=service,
        severity=severity,
        user_message=text,
    )


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
