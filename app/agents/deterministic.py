"""Deterministic agent loop for local demos/tests without an LLM API key.

Mirrors the CrewAI workflow: observe → investigate → RCA → plan → safety → act → verify.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.enums import IncidentStatus, RiskLevel
from app.policies.safety import evaluate_action
from app.services.incident_service import IncidentService
from app.tools.context import current_incident_id
from app.tools.mock_state import mock_infra
from app.tools.ops_tools import (
    GetCloudWatchAlarmTool,
    GetPm2StatusTool,
    GetSystemMetricsTool,
    QueryLogsTool,
    RestartPm2ProcessTool,
)


def run_deterministic_incident(db: Session, incident_id: str) -> dict[str, Any]:
    service = IncidentService(db)
    incident = service.get(incident_id)
    if not incident:
        raise ValueError(f"Incident not found: {incident_id}")

    token = current_incident_id.set(incident_id)
    try:
        service.transition(incident, IncidentStatus.TRIAGING)
        alarm = json.loads(
            GetCloudWatchAlarmTool()._run(alarm_name="prod-api-high-latency")
        )
        service.add_observation(
            incident_id,
            source="cloudwatch",
            name="alarm",
            value=alarm["state"],
            evidence=alarm,
        )

        service.transition(incident, IncidentStatus.INVESTIGATING)
        metrics = json.loads(GetSystemMetricsTool()._run())
        pm2 = json.loads(GetPm2StatusTool()._run())
        logs = json.loads(
            QueryLogsTool()._run(service=incident.service, time_range_minutes=30)
        )

        for key, value in metrics["metrics"].items():
            service.add_observation(
                incident_id,
                source="system",
                name=key,
                value=str(value),
                evidence={"value": value},
            )
        service.add_observation(
            incident_id,
            source="pm2",
            name="process_status",
            value=json.dumps(pm2["processes"]),
            evidence=pm2,
        )
        service.add_observation(
            incident_id,
            source="logs",
            name="recent_errors",
            value="\n".join(logs["lines"]),
            evidence=logs,
        )

        before_latency = str(metrics["metrics"]["api_p95_latency_ms"])
        before_memory = str(metrics["metrics"]["memory_utilization"])

        service.transition(incident, IncidentStatus.HYPOTHESIS_READY)
        hypotheses = [
            {
                "hypothesis": "Unhealthy Node API process leaking memory under load",
                "evidence_for": (
                    f"memory={metrics['metrics']['memory_utilization']}%, "
                    f"swap={metrics['metrics']['swap_utilization']}%, "
                    "PM2 api process marked unhealthy with elevated restarts"
                ),
                "evidence_against": "CPU remains moderate",
                "score": 0.86,
                "selected": True,
            },
            {
                "hypothesis": "MySQL connection saturation is the primary cause",
                "evidence_for": f"mysql_connections={metrics['metrics']['mysql_connections']}",
                "evidence_against": "API process itself shows memory growth and restarts",
                "score": 0.42,
                "selected": False,
            },
            {
                "hypothesis": "Disk exhaustion",
                "evidence_for": "None strong",
                "evidence_against": f"disk={metrics['metrics']['disk_utilization']}%",
                "score": 0.08,
                "selected": False,
            },
        ]
        selected = hypotheses[0]
        for item in hypotheses:
            service.add_hypothesis(incident_id, **item)

        incident.root_cause = selected["hypothesis"]
        incident.confidence = selected["score"]
        db.commit()

        service.transition(incident, IncidentStatus.PLAN_READY)
        proposed_action = "restart_pm2_process"
        parameters = {"process_name": "api"}
        decision = evaluate_action(
            proposed_action,
            parameters,
            already_approved=False,
            actions_already_taken=service.count_actions(incident_id),
        )
        plan = service.add_plan(
            incident_id,
            proposed_action=proposed_action,
            parameters=parameters,
            risk=decision.risk.value,
            rationale=(
                "Lowest-risk allowlisted remediation: restart unhealthy PM2 api process "
                "via controlled template, then verify latency and memory."
            ),
            approval_required=decision.approval_required,
            approved=decision.allowed and not decision.approval_required,
            approved_by="policy-auto" if decision.allowed else None,
        )

        if decision.approval_required and not plan.approved:
            service.transition(incident, IncidentStatus.AWAITING_APPROVAL)
            return {
                "status": IncidentStatus.AWAITING_APPROVAL.value,
                "message": "Plan awaiting human approval",
            }

        if not decision.allowed:
            service.finalize(
                incident,
                status=IncidentStatus.ESCALATED,
                summary="Safety policy blocked remediation",
                root_cause=selected["hypothesis"],
                confidence=selected["score"],
            )
            return {"status": IncidentStatus.ESCALATED.value, "reason": decision.reason}

        service.transition(incident, IncidentStatus.EXECUTING)
        action_raw = RestartPm2ProcessTool()._run(process_name="api")
        action_result = json.loads(action_raw)
        service.add_action(
            incident_id,
            tool=proposed_action,
            parameters=parameters,
            approved_by=plan.approved_by or "policy-auto",
            result=action_raw,
            success=bool(action_result.get("success")),
        )
        service.add_audit(
            incident_id,
            actor="action-agent",
            action="execute_tool",
            details={"tool": proposed_action, "parameters": parameters},
            result=action_raw,
        )

        service.transition(incident, IncidentStatus.VERIFYING)
        after = mock_infra.get(incident_id)
        after_latency = str(after["metrics"]["api_p95_latency_ms"])
        after_memory = str(after["metrics"]["memory_utilization"])
        latency_ok = float(after["metrics"]["api_p95_latency_ms"]) < 500
        memory_ok = float(after["metrics"]["memory_utilization"]) < 75
        alarm_ok = after["alarm"]["state"] == "OK"
        api_healthy = all(
            (not p.get("unhealthy"))
            for p in after["pm2"]["processes"]
            if p["name"] == "api"
        )
        recovered = latency_ok and memory_ok and alarm_ok and api_healthy

        service.add_verification(
            incident_id,
            metric="api_p95_latency_ms",
            before_value=before_latency,
            after_value=after_latency,
            success=latency_ok,
        )
        service.add_verification(
            incident_id,
            metric="memory_utilization",
            before_value=before_memory,
            after_value=after_memory,
            success=memory_ok,
        )
        service.add_verification(
            incident_id,
            metric="alarm_state",
            before_value=alarm["state"],
            after_value=after["alarm"]["state"],
            success=alarm_ok,
        )

        summary = (
            "Detected API latency alarm, correlated high memory/swap with unhealthy "
            "PM2 api process, restarted api via allowlisted action, and verified recovery."
        )
        final_status = (
            IncidentStatus.RECOVERED if recovered else IncidentStatus.FAILED
        )
        service.finalize(
            incident,
            status=final_status,
            summary=summary,
            root_cause=selected["hypothesis"],
            confidence=selected["score"],
        )
        return {
            "status": final_status.value,
            "root_cause": selected["hypothesis"],
            "confidence": selected["score"],
            "risk": RiskLevel.LOW.value,
            "action": proposed_action,
        }
    finally:
        current_incident_id.reset(token)