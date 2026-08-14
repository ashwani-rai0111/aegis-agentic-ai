from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.schemas import (
    ApproveRequest,
    IncidentDetail,
    IncidentSummary,
    InvestigateRequest,
    LiveIncidentRequest,
    RejectRequest,
    SimulateRequest,
)
from app.services.auth import RequireSession
from app.services.incident_service import IncidentService
from app.services.orchestrator import (
    approve_and_resume,
    investigate_user_issue,
    reject_and_escalate,
    run_live_incident,
    simulate_incident,
)

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.post("/simulate", response_model=IncidentDetail)
def simulate(
    payload: SimulateRequest,
    _: RequireSession,
    db: Session = Depends(get_db),
) -> IncidentDetail:
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


@router.post("/live", response_model=IncidentDetail)
def live_incident(
    payload: LiveIncidentRequest,
    _: RequireSession,
    db: Session = Depends(get_db),
) -> IncidentDetail:
    try:
        outcome = run_live_incident(
            db,
            service=payload.service,
            severity=payload.severity,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Live incident failed: {exc}") from exc

    incident = outcome["incident"]
    if not incident:
        raise HTTPException(status_code=500, detail="Incident missing after live run")
    return IncidentDetail.model_validate(incident)


@router.post("/investigate", response_model=IncidentDetail)
def investigate(
    payload: InvestigateRequest,
    _: RequireSession,
    db: Session = Depends(get_db),
) -> IncidentDetail:
    try:
        outcome = investigate_user_issue(
            db,
            message=payload.message,
            service=payload.service,
            severity=payload.severity,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=500, detail=f"Investigation failed: {exc}"
        ) from exc

    incident = outcome["incident"]
    if not incident:
        raise HTTPException(status_code=500, detail="Incident missing after investigation")
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
    _: RequireSession,
    db: Session = Depends(get_db),
) -> IncidentDetail:
    try:
        outcome = approve_and_resume(
            db, incident_id, approved_by=payload.approved_by
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Approve/resume failed: {exc}") from exc

    incident = outcome["incident"]
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return IncidentDetail.model_validate(incident)


@router.post("/{incident_id}/reject", response_model=IncidentDetail)
def reject_incident(
    incident_id: str,
    payload: RejectRequest,
    _: RequireSession,
    db: Session = Depends(get_db),
) -> IncidentDetail:
    try:
        outcome = reject_and_escalate(
            db,
            incident_id,
            rejected_by=payload.rejected_by,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    incident = outcome["incident"]
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return IncidentDetail.model_validate(incident)
