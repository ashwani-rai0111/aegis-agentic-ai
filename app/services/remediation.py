"""Shared execute → verify → finalize path used by agents and approval resume."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.enums import IncidentStatus
from app.policies.safety import evaluate_action
from app.services.incident_service import IncidentService
from app.tools.context import current_incident_id
from app.tools.mock_state import mock_infra
from app.tools.ops_tools import HealthCheckTool, execute_action_tool


def verify_recovery(incident_id: str, before: dict[str, Any]) -> dict[str, Any]:
    after = mock_infra.get(incident_id)
    health = json.loads(HealthCheckTool()._run())
    latency_ok = float(after["metrics"]["api_p95_latency_ms"]) < 500
    memory_ok = float(after["metrics"]["memory_utilization"]) < 75
    alarm_ok = after["alarm"]["state"] == "OK"
    http_ok = int(health["health"]["http_status"]) == 200
    pm2_ok = all(not p.get("unhealthy") for p in after["pm2"]["processes"])
    mysql_ok = bool(after.get("mysql", {}).get("healthy", True))
    recovered = latency_ok and memory_ok and alarm_ok and http_ok and pm2_ok and mysql_ok
    return {
        "after": after,
        "health": health,
        "checks": {
            "api_p95_latency_ms": (
                str(before["metrics"]["api_p95_latency_ms"]),
                str(after["metrics"]["api_p95_latency_ms"]),
                latency_ok,
            ),
            "memory_utilization": (
                str(before["metrics"]["memory_utilization"]),
                str(after["metrics"]["memory_utilization"]),
                memory_ok,
            ),
            "alarm_state": (
                before["alarm"]["state"],
                after["alarm"]["state"],
                alarm_ok,
            ),
            "http_health": (
                str(before.get("health", {}).get("http_status", "?")),
                str(health["health"]["http_status"]),
                http_ok,
            ),
        },
        "recovered": recovered,
    }


def execute_approved_plan(
    db: Session,
    incident_id: str,
    *,
    already_approved: bool = False,
    summary: str | None = None,
) -> dict[str, Any]:
    """Run safety check → execute tool → verify → finalize.

    Caller must ensure incident is at PLAN_READY or AWAITING_APPROVAL/EXECUTING
    as appropriate. This function transitions EXECUTING → VERIFYING → terminal.
    """
    service = IncidentService(db)
    incident = service.get(incident_id)
    if not incident:
        raise ValueError(f"Incident not found: {incident_id}")

    plan = service.latest_plan(incident_id)
    if not plan:
        raise ValueError("No remediation plan available")

    token = current_incident_id.set(incident_id)
    try:
        before = mock_infra.get(incident_id)
        decision = evaluate_action(
            plan.proposed_action,
            plan.parameters or {},
            already_approved=already_approved or bool(plan.approved),
            actions_already_taken=service.count_actions(incident_id),
        )

        if decision.approval_required and not (already_approved or plan.approved):
            if incident.status == IncidentStatus.PLAN_READY.value:
                service.transition(incident, IncidentStatus.AWAITING_APPROVAL)
            return {
                "status": IncidentStatus.AWAITING_APPROVAL.value,
                "message": (
                    f"I recommend {plan.proposed_action} because: {plan.rationale}. "
                    "Approve?"
                ),
                "risk": decision.risk.value,
            }

        if not decision.allowed:
            service.finalize(
                incident,
                status=IncidentStatus.ESCALATED,
                summary=summary or "Safety policy blocked the proposed remediation",
                root_cause=incident.root_cause or "unknown",
                confidence=float(incident.confidence or 0.0),
            )
            return {
                "status": IncidentStatus.ESCALATED.value,
                "reason": decision.reason,
            }

        if incident.status == IncidentStatus.PLAN_READY.value:
            service.transition(incident, IncidentStatus.EXECUTING)
        elif incident.status == IncidentStatus.AWAITING_APPROVAL.value:
            service.transition(incident, IncidentStatus.EXECUTING)
        # If already EXECUTING (post-approve), continue.

        action_raw = execute_action_tool(plan.proposed_action, plan.parameters or {})
        action_result = json.loads(action_raw)
        service.add_action(
            incident_id,
            tool=plan.proposed_action,
            parameters=plan.parameters or {},
            approved_by=plan.approved_by or ("policy-auto" if not decision.approval_required else None),
            result=action_raw,
            success=bool(action_result.get("success")),
        )
        service.add_audit(
            incident_id,
            actor="recovery-agent",
            action="execute_tool",
            details={
                "tool": plan.proposed_action,
                "parameters": plan.parameters,
                "risk": decision.risk.value,
            },
            result=action_raw,
        )

        service.transition(incident, IncidentStatus.VERIFYING)
        verification = verify_recovery(incident_id, before)
        for metric, (before_v, after_v, ok) in verification["checks"].items():
            service.add_verification(
                incident_id,
                metric=metric,
                before_value=before_v,
                after_value=after_v,
                success=ok,
            )

        recovered = verification["recovered"] and bool(action_result.get("success"))
        final_status = IncidentStatus.RECOVERED if recovered else IncidentStatus.FAILED
        final_summary = summary or (
            "Agents investigated with tools, selected a root cause, applied a "
            f"{decision.risk.value}-risk remediation ({plan.proposed_action}), "
            "and verified recovery against latency, memory, alarm, and HTTP health."
            if recovered
            else "Remediation executed but verification did not confirm full recovery."
        )
        service.finalize(
            incident,
            status=final_status,
            summary=final_summary,
            root_cause=incident.root_cause or plan.rationale,
            confidence=float(incident.confidence or 0.7),
        )
        return {
            "status": final_status.value,
            "root_cause": incident.root_cause,
            "confidence": incident.confidence,
            "action": plan.proposed_action,
            "risk": decision.risk.value,
            "recovered": recovered,
        }
    finally:
        current_incident_id.reset(token)


def reject_plan(
    db: Session,
    incident_id: str,
    *,
    rejected_by: str,
    reason: str = "Operator rejected remediation plan",
) -> dict[str, Any]:
    service = IncidentService(db)
    incident = service.get(incident_id)
    if not incident:
        raise ValueError(f"Incident not found: {incident_id}")
    if incident.status != IncidentStatus.AWAITING_APPROVAL.value:
        raise ValueError(f"Incident is not awaiting approval (status={incident.status})")

    plan = service.latest_plan(incident_id)
    service.add_audit(
        incident_id,
        actor=rejected_by,
        action="plan_rejected",
        details={
            "proposed_action": plan.proposed_action if plan else None,
            "reason": reason,
        },
        result="rejected",
    )
    service.finalize(
        incident,
        status=IncidentStatus.ESCALATED,
        summary=reason,
        root_cause=incident.root_cause or "unresolved",
        confidence=float(incident.confidence or 0.0),
    )
    return {"status": IncidentStatus.ESCALATED.value, "reason": reason}
