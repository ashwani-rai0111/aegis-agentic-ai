from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.db import (
    Action,
    AuditLog,
    Hypothesis,
    Incident,
    Observation,
    Plan,
    Verification,
)
from app.models.enums import ALLOWED_TRANSITIONS, IncidentStatus


class InvalidTransitionError(ValueError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IncidentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_incident(
        self,
        *,
        service: str,
        severity: str,
        scenario: str,
        summary: str,
        agent_mode: str | None = None,
    ) -> Incident:
        incident = Incident(
            service=service,
            severity=severity,
            status=IncidentStatus.DETECTED.value,
            summary=summary,
            scenario=scenario,
            agent_mode=agent_mode,
        )
        self.db.add(incident)
        self.db.flush()
        self.add_audit(
            incident.id,
            actor="system",
            action="incident_created",
            details={"scenario": scenario, "severity": severity},
            result="DETECTED",
        )
        self.db.commit()
        self.db.refresh(incident)
        return incident

    def get(self, incident_id: str) -> Incident | None:
        stmt = (
            select(Incident)
            .where(Incident.id == incident_id)
            .options(
                selectinload(Incident.observations),
                selectinload(Incident.hypotheses),
                selectinload(Incident.plans),
                selectinload(Incident.actions),
                selectinload(Incident.verifications),
                selectinload(Incident.audit_logs),
            )
        )
        return self.db.scalar(stmt)

    def list_incidents(self) -> list[Incident]:
        stmt = select(Incident).order_by(Incident.detected_at.desc())
        return list(self.db.scalars(stmt).all())

    def transition(self, incident: Incident, new_status: IncidentStatus) -> Incident:
        current = IncidentStatus(incident.status)
        allowed = ALLOWED_TRANSITIONS.get(current, set())
        if new_status not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition from {current.value} to {new_status.value}"
            )
        incident.status = new_status.value
        incident.updated_at = _utcnow()
        self.add_audit(
            incident.id,
            actor="orchestrator",
            action="status_transition",
            details={"from": current.value, "to": new_status.value},
            result=new_status.value,
        )
        self.db.commit()
        self.db.refresh(incident)
        return incident

    def add_observation(
        self,
        incident_id: str,
        *,
        source: str,
        name: str,
        value: str,
        evidence: dict[str, Any] | None = None,
    ) -> Observation:
        row = Observation(
            incident_id=incident_id,
            source=source,
            name=name,
            value=value,
            evidence=evidence,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def add_hypothesis(
        self,
        incident_id: str,
        *,
        hypothesis: str,
        evidence_for: str,
        evidence_against: str,
        score: float,
        selected: bool = False,
    ) -> Hypothesis:
        row = Hypothesis(
            incident_id=incident_id,
            hypothesis=hypothesis,
            evidence_for=evidence_for,
            evidence_against=evidence_against,
            score=score,
            selected=selected,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def add_plan(
        self,
        incident_id: str,
        *,
        proposed_action: str,
        parameters: dict[str, Any],
        risk: str,
        rationale: str,
        approval_required: bool,
        approved: bool = False,
        approved_by: str | None = None,
    ) -> Plan:
        row = Plan(
            incident_id=incident_id,
            proposed_action=proposed_action,
            parameters=parameters,
            risk=risk,
            rationale=rationale,
            approval_required=approval_required,
            approved=approved,
            approved_by=approved_by,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def latest_plan(self, incident_id: str) -> Plan | None:
        stmt = (
            select(Plan)
            .where(Plan.incident_id == incident_id)
            .order_by(Plan.id.desc())
        )
        return self.db.scalars(stmt).first()

    def approve_latest_plan(self, incident_id: str, approved_by: str) -> Plan:
        plan = self.latest_plan(incident_id)
        if not plan:
            raise ValueError("No plan to approve")
        plan.approved = True
        plan.approved_by = approved_by
        self.add_audit(
            incident_id,
            actor=approved_by,
            action="plan_approved",
            details={"proposed_action": plan.proposed_action},
            result="approved",
        )
        self.db.commit()
        self.db.refresh(plan)
        return plan

    def add_action(
        self,
        incident_id: str,
        *,
        tool: str,
        parameters: dict[str, Any] | None,
        approved_by: str | None,
        result: str,
        success: bool,
    ) -> Action:
        now = _utcnow()
        row = Action(
            incident_id=incident_id,
            tool=tool,
            parameters=parameters,
            approved_by=approved_by,
            started_at=now,
            completed_at=now,
            result=result,
            success=success,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def count_actions(self, incident_id: str) -> int:
        stmt = select(Action).where(Action.incident_id == incident_id)
        return len(list(self.db.scalars(stmt).all()))

    def add_verification(
        self,
        incident_id: str,
        *,
        metric: str,
        before_value: str,
        after_value: str,
        success: bool,
    ) -> Verification:
        row = Verification(
            incident_id=incident_id,
            metric=metric,
            before_value=before_value,
            after_value=after_value,
            success=success,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def finalize(
        self,
        incident: Incident,
        *,
        status: IncidentStatus,
        summary: str,
        root_cause: str,
        confidence: float,
    ) -> Incident:
        incident.summary = summary
        incident.root_cause = root_cause
        incident.confidence = confidence
        return self.transition(incident, status)

    def add_audit(
        self,
        incident_id: str | None,
        *,
        actor: str,
        action: str,
        details: dict[str, Any] | None = None,
        result: str | None = None,
    ) -> AuditLog:
        row = AuditLog(
            incident_id=incident_id,
            actor=actor,
            action=action,
            details=details,
            result=result,
        )
        self.db.add(row)
        # caller may commit; flush so it is part of the current transaction
        self.db.flush()
        return row