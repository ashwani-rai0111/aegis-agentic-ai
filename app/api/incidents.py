from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.enums import IncidentStatus
from app.models.schemas import (
    ApproveRequest,
    IncidentDetail,
    IncidentSummary,
    SimulateRequest,
)
from app.services.incident_service import IncidentService, InvalidTransitionError
from app.services.orchestrator import simulate_incident

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.post("/simulate", response_model=IncidentDetail)
def simulate(payload: SimulateRequest, db: Session = Depends(get_db)) -> IncidentDetail:
    try:
        outcome = simulate_incident(
            db,
            scenario=payload.scenario,
            service=payload.service,
            severity=payload.severity,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - surfaced to client for demo debugging
        raise HTTPException(status_code=500, detail=f"Simulation failed: {exc}") from exc

    incident = outcome["incident"]
    if not incident:
        raise HTTPException(status_code=500, detail="Incident missing after simulation")
    return IncidentDetail.model_validate(incident)


@router.get("", response_model=list[IncidentSummary])
def list_incidents(db: Session = Depends(get_db)) -> list[IncidentSummary]:
    rows = IncidentService(db).list_incidents()
    return [IncidentSummary.model_validate(row) for row in rows]


@router.get("/{incident_id}", response_model=IncidentDetail)
def get_incident(incident_id: str, db: Session = Depends(get_db)) -> IncidentDetail:
    incident = IncidentService(db).get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return IncidentDetail.model_validate(incident)


@router.post("/{incident_id}/approve", response_model=IncidentDetail)
def approve_incident(
    incident_id: str,
    payload: ApproveRequest,
    db: Session = Depends(get_db),
) -> IncidentDetail:
    service = IncidentService(db)
    incident = service.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.status != IncidentStatus.AWAITING_APPROVAL.value:
        raise HTTPException(
            status_code=400,
            detail=f"Incident is not awaiting approval (status={incident.status})",
        )
    try:
        service.approve_latest_plan(incident_id, payload.approved_by)
        service.transition(incident, IncidentStatus.EXECUTING)
    except (ValueError, InvalidTransitionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # For MVP, approval endpoint marks plan approved; full resume can be added later.
    refreshed = service.get(incident_id)
    return IncidentDetail.model_validate(refreshed)