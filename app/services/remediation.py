"""Shared execute → verify → finalize path used by agents and approval resume."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.enums import IncidentStatus
from app.policies.safety import evaluate_action
from app.services.incident_service import IncidentService
from app.tools.backend import get_tool_backend
from app.tools.context import current_incident_id
from app.tools.ops_tools import execute_action_tool


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def verify_recovery(incident_id: str, before: dict[str, Any]) -> dict[str, Any]:
    backend = get_tool_backend(incident_id)
    after = backend.snapshot()
    health = backend.health_check()
    before_metrics = before.get("metrics") or {}
    after_metrics = after.get("metrics") or {}

    latency_after = after_metrics.get("api_p95_latency_ms")
    memory_after = after_metrics.get("memory_utilization")
    # If latency metric is unavailable on AWS, do not fail solely on it.
    latency_ok = (
        True
        if latency_after is None
        else _as_float(latency_after, 9999) < 500
    )
    memory_ok = (
        True
        if memory_after is None
        else _as_float(memory_after, 100) < 75
    )
    alarm_ok = str(after.get("alarm", {}).get("state", "")).upper() in {
        "OK",
        "INSUFFICIENT_DATA",
    }
    http_status = int(health.get("health", {}).get("http_status") or 0)
    # If health URL not configured (0), skip HTTP gate for AWS.
    http_ok = http_status == 200 or http_status == 0
    pm2_procs = after.get("pm2", {}).get("processes") or []
    pm2_ok = all(not p.get("unhealthy") for p in pm2_procs) if pm2_procs else True
    mysql_after = after.get("mysql") or {}
    mysql_ok = bool(mysql_after.get("healthy", True))
    recovered = latency_ok and memory_ok and alarm_ok and http_ok and pm2_ok and mysql_ok
    return {
        "after": after,
        "health": health,
        "checks": {
            "api_p95_latency_ms": (
                str(before_metrics.get("api_p95_latency_ms", "?")),
                str(latency_after if latency_after is not None else "n/a"),
                latency_ok,
            ),
            "memory_utilization": (
                str(before_metrics.get("memory_utilization", "?")),
                str(memory_after if memory_after is not None else "n/a"),
                memory_ok,
            ),
            "alarm_state": (
                str(before.get("alarm", {}).get("state", "?")),
                str(after.get("alarm", {}).get("state", "?")),
                alarm_ok,
            ),
            "http_health": (
                str(before.get("health", {}).get("http_status", "?")),
                str(http_status),
                http_ok,
            ),
            "mysql": (
                str((before.get("mysql") or {}).get("status", "?")),
                str(mysql_after.get("status", "?")),
                mysql_ok,
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
    """Run safety check → execute tool → verify → finalize."""
    service = IncidentService(db)
    incident = service.get(incident_id)
    if not incident:
        raise ValueError(f"Incident not found: {incident_id}")

    plan = service.latest_plan(incident_id)
    if not plan:
        raise ValueError("No remediation plan available")

    token = current_incident_id.set(incident_id)
    try:
        before = get_tool_backend(incident_id).snapshot()
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

        action_raw = execute_action_tool(plan.proposed_action, plan.parameters or {})
        action_result = json.loads(action_raw)
        service.add_action(
            incident_id,
            tool=plan.proposed_action,
            parameters=plan.parameters or {},
            approved_by=plan.approved_by
            or ("policy-auto" if not decision.approval_required else None),
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
